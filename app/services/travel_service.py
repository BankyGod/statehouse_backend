from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.character import Character
from app.models.enterprise import StateEnterprise
from app.models.permit import Permit, PermitStatus, PermitType
from app.models.state import State
from app.models.transport import TransportCarrier, TransportMode
from app.models.travel import TravelLog
from app.services.character_service import ensure_not_jailed


async def ensure_carriers_seeded(db: AsyncSession) -> int:
    """Keep exactly the six government SOE carriers active; retire all others."""
    from app.models.transport import CarrierOwnership
    from app.seed.transport_data import CARRIERS
    from app.services import enterprise_service

    await enterprise_service.ensure_enterprises_seeded(db)

    enterprises = {
        e.slug: e
        for e in (await db.execute(select(StateEnterprise))).scalars().all()
    }
    by_slug = {
        c.slug: c
        for c in (await db.execute(select(TransportCarrier))).scalars().all()
    }
    keep_slugs = {raw["slug"] for raw in CARRIERS}
    created = 0
    for raw in CARRIERS:
        ent = enterprises.get(raw["enterprise_slug"]) if raw.get("enterprise_slug") else None
        row = by_slug.get(raw["slug"])
        if row is None:
            db.add(
                TransportCarrier(
                    slug=raw["slug"],
                    name=raw["name"],
                    mode=raw["mode"],
                    ownership=CarrierOwnership.GOVERNMENT,
                    enterprise_id=ent.id if ent else None,
                    base_fare_mult=raw["base_fare_mult"],
                    time_mult=raw["time_mult"],
                    comfort=raw["comfort"],
                    reliability=raw["reliability"],
                    tagline=raw["tagline"],
                    is_active=True,
                )
            )
            created += 1
        else:
            row.name = raw["name"]
            row.mode = raw["mode"]
            row.ownership = CarrierOwnership.GOVERNMENT
            row.enterprise_id = ent.id if ent else row.enterprise_id
            row.base_fare_mult = raw["base_fare_mult"]
            row.time_mult = raw["time_mult"]
            row.comfort = raw["comfort"]
            row.reliability = raw["reliability"]
            row.tagline = raw["tagline"]
            row.is_active = True

    # Deactivate private / leftover carriers so travel only offers SOE operators
    for slug, row in by_slug.items():
        if slug not in keep_slugs:
            row.is_active = False

    await db.flush()
    return created


def base_hop(from_state_id: int, to_state_id: int) -> dict:
    settings = get_settings()
    hop = abs(to_state_id - from_state_id)
    cost = settings.travel_base_cost + hop * 3.0
    minutes = settings.travel_base_minutes + hop * 2
    return {"cost": round(cost, 2), "minutes": minutes, "hop": hop}


def quote_travel(from_state_id: int, to_state_id: int) -> dict:
    """Legacy quote without carrier (average mid-tier)."""
    base = base_hop(from_state_id, to_state_id)
    return {"cost": base["cost"], "minutes": base["minutes"]}


def _quote_with_carrier(
    from_state_id: int, to_state_id: int, carrier: TransportCarrier
) -> dict:
    base = base_hop(from_state_id, to_state_id)
    cost = round(base["cost"] * carrier.base_fare_mult, 2)
    minutes = max(8, int(round(base["minutes"] * carrier.time_mult)))
    return {"cost": cost, "minutes": minutes}


async def _has_travel_permit(
    db: AsyncSession, character: Character, state_id: int
) -> bool:
    if character.home_state_id == state_id:
        return True
    result = await db.execute(
        select(Permit).where(
            Permit.character_id == character.id,
            Permit.state_id == state_id,
            Permit.permit_type == PermitType.TRAVEL,
            Permit.status == PermitStatus.ACTIVE,
            Permit.expires_at > utcnow(),
        )
    )
    return result.scalar_one_or_none() is not None


def _permit_discount_mult(mode: TransportMode) -> float:
    """Travel permit: 25% off bus/rail; 10% off air."""
    if mode in (TransportMode.BUS, TransportMode.RAIL):
        return 0.75
    if mode == TransportMode.AIR:
        return 0.90
    return 1.0


async def list_travel_options(
    db: AsyncSession, character: Character, to_state_id: int
) -> list[dict]:
    await ensure_carriers_seeded(db)
    if to_state_id == character.current_state_id:
        raise HTTPException(status_code=400, detail="Already in that state")
    dest = await db.get(State, to_state_id)
    if dest is None or not dest.is_open:
        raise HTTPException(status_code=404, detail="Destination state not found")

    has_permit = await _has_travel_permit(db, character, to_state_id)
    from app.models.transport import CarrierOwnership

    carriers = (
        await db.execute(
            select(TransportCarrier)
            .where(
                TransportCarrier.is_active.is_(True),
                TransportCarrier.ownership == CarrierOwnership.GOVERNMENT,
            )
            .order_by(TransportCarrier.mode, TransportCarrier.base_fare_mult)
        )
    ).scalars().all()

    options = []
    for carrier in carriers:
        q = _quote_with_carrier(
            character.current_state_id, to_state_id, carrier
        )
        disc_mult = _permit_discount_mult(carrier.mode) if has_permit else 1.0
        discounted = round(q["cost"] * disc_mult, 2) if has_permit else None
        ent_name = None
        if carrier.enterprise_id:
            ent = await db.get(StateEnterprise, carrier.enterprise_id)
            ent_name = ent.name if ent else None
        options.append(
            {
                "carrier_id": carrier.id,
                "carrier_slug": carrier.slug,
                "carrier_name": carrier.name,
                "mode": carrier.mode.value,
                "ownership": "government",
                "enterprise_id": carrier.enterprise_id,
                "enterprise_name": ent_name,
                "tagline": carrier.tagline,
                "comfort": carrier.comfort,
                "reliability": carrier.reliability,
                "cost": q["cost"],
                "minutes": q["minutes"],
                "discounted_cost": discounted,
                "permit_applies": has_permit,
                "to_state_id": to_state_id,
                "to_state_name": dest.name,
                "from_state_id": character.current_state_id,
            }
        )
    return options


async def quote_carrier(
    db: AsyncSession,
    character: Character,
    to_state_id: int,
    carrier_id: int,
) -> dict:
    await ensure_carriers_seeded(db)
    from app.models.transport import CarrierOwnership

    carrier = await db.get(TransportCarrier, carrier_id)
    if (
        carrier is None
        or not carrier.is_active
        or carrier.ownership != CarrierOwnership.GOVERNMENT
    ):
        raise HTTPException(status_code=404, detail="Carrier not found")
    dest = await db.get(State, to_state_id)
    if dest is None:
        raise HTTPException(status_code=404, detail="Destination state not found")
    q = _quote_with_carrier(character.current_state_id, to_state_id, carrier)
    has_permit = await _has_travel_permit(db, character, to_state_id)
    disc_mult = _permit_discount_mult(carrier.mode) if has_permit else 1.0
    return {
        "from_state_id": character.current_state_id,
        "to_state_id": to_state_id,
        "carrier_id": carrier.id,
        "carrier_name": carrier.name,
        "mode": carrier.mode.value,
        "ownership": "government",
        "enterprise_id": carrier.enterprise_id,
        "cost": q["cost"],
        "minutes": q["minutes"],
        "discounted_cost": round(q["cost"] * disc_mult, 2) if has_permit else None,
        "permit_applies": has_permit,
    }


async def _route_travel_fare(
    db: AsyncSession,
    cost: float,
    *,
    carrier: TransportCarrier | None,
    character_id: int | None,
) -> dict:
    """Split fare: VAT → treasury; remainder → linked SOE (or infra fee if private)."""
    from app.models.treasury import TreasuryTxType
    from app.services import treasury_service

    cost = round(float(cost), 2)
    if cost <= 0:
        return {"vat": 0.0, "operator": 0.0, "enterprise_id": None}

    vat = round(cost * 0.05, 2)
    operator = round(cost - vat, 2)
    if vat > 0:
        await treasury_service.credit(
            db,
            vat,
            TreasuryTxType.FEE,
            note="Travel VAT",
            character_id=character_id,
        )

    enterprise_id = None
    if carrier and carrier.enterprise_id:
        ent = await db.get(StateEnterprise, carrier.enterprise_id)
        if ent:
            ent.cash_balance = round(float(ent.cash_balance or 0) + operator, 2)
            ent.lifetime_revenue = round(float(ent.lifetime_revenue or 0) + operator, 2)
            enterprise_id = ent.id
            operator = 0.0
    elif carrier and getattr(carrier.ownership, "value", str(carrier.ownership)) == "government":
        await treasury_service.credit(
            db,
            operator,
            TreasuryTxType.FEE,
            note=f"Gov carrier fare — {carrier.name}",
            character_id=character_id,
        )
        operator = 0.0
    else:
        # Private / independent: infrastructure levy to treasury
        levy = round(operator * 0.15, 2)
        if levy > 0:
            await treasury_service.credit(
                db,
                levy,
                TreasuryTxType.FEE,
                note="Travel infrastructure levy",
                character_id=character_id,
            )
        operator = round(operator - levy, 2)

    await db.flush()
    return {"vat": vat, "operator": operator, "enterprise_id": enterprise_id}


async def start_travel(
    db: AsyncSession,
    character: Character,
    to_state_id: int,
    carrier_id: int | None = None,
) -> dict:
    ensure_not_jailed(character)
    await ensure_carriers_seeded(db)
    if character.is_traveling:
        raise HTTPException(status_code=400, detail="Already traveling")
    if to_state_id == character.current_state_id:
        raise HTTPException(status_code=400, detail="Already in that state")

    dest = await db.get(State, to_state_id)
    if dest is None:
        raise HTTPException(status_code=404, detail="Destination state not found")

    from app.models.transport import CarrierOwnership

    carrier: TransportCarrier | None = None
    if carrier_id is not None:
        carrier = await db.get(TransportCarrier, carrier_id)
        if (
            carrier is None
            or not carrier.is_active
            or carrier.ownership != CarrierOwnership.GOVERNMENT
        ):
            raise HTTPException(
                status_code=404, detail="Government carrier not found"
            )
    else:
        # Legacy clients: default to cheapest active state carrier
        result = await db.execute(
            select(TransportCarrier)
            .where(
                TransportCarrier.is_active.is_(True),
                TransportCarrier.ownership == CarrierOwnership.GOVERNMENT,
            )
            .order_by(TransportCarrier.base_fare_mult.asc())
            .limit(1)
        )
        carrier = result.scalar_one_or_none()

    if carrier is None:
        quote = quote_travel(character.current_state_id, to_state_id)
        cost = quote["cost"]
        minutes = quote["minutes"]
        mode = None
        carrier_name = "Independent travel"
        cid = None
        if await _has_travel_permit(db, character, to_state_id):
            cost = round(cost * 0.75, 2)
    else:
        q = _quote_with_carrier(character.current_state_id, to_state_id, carrier)
        cost = q["cost"]
        minutes = q["minutes"]
        mode = carrier.mode
        carrier_name = carrier.name
        cid = carrier.id
        if await _has_travel_permit(db, character, to_state_id):
            cost = round(cost * _permit_discount_mult(carrier.mode), 2)

    # Enacted transport bills can lower fares (travel_mult on nation.notes)
    from app.services import politics_service

    nation = await politics_service.get_or_create_nation(db)
    notes = nation.notes or ""
    if "travel_mult=" in notes:
        try:
            raw = notes.rsplit("travel_mult=", 1)[-1].split("|")[0]
            mult = min(1.0, max(0.7, float(raw)))
            cost = round(cost * mult, 2)
        except ValueError:
            pass

    # Private fuel / travel cover from marketplace
    cond = character.condition or ""
    if "fuel_until:" in cond:
        try:
            from datetime import datetime, timezone

            from app.core.game_time import utcnow as _utcnow

            raw = cond.split("fuel_until:")[-1].split("|")[0]
            until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > _utcnow():
                cost = round(cost * 0.85, 2)
        except Exception:
            pass

    if character.heat >= 60:
        raise HTTPException(
            status_code=403,
            detail="Travel denied: security alert (heat too high)",
        )

    if character.cash < cost:
        raise HTTPException(status_code=400, detail="Insufficient funds for travel")

    now = utcnow()
    arrives = now + timedelta(minutes=minutes)
    character.cash -= cost
    await _route_travel_fare(db, cost, carrier=carrier, character_id=character.id)
    character.is_traveling = True
    character.travel_until = arrives
    character.travel_destination_id = to_state_id

    mode_label = mode.value if mode else "travel"
    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.TRAVEL,
        status=ActivityStatus.IN_PROGRESS,
        title=f"{carrier_name} to {dest.name}",
        description=f"In transit to {dest.capital} via {carrier_name} ({mode_label})",
        age_gain_years=0,
        cash_delta=-cost,
        started_at=now,
        completes_at=arrives,
        ref_type="state",
        ref_id=to_state_id,
    )
    db.add(activity)
    await db.flush()
    from app.services.notify_service import broadcast_activity, broadcast_character

    await broadcast_activity(activity)
    await broadcast_character(character)

    log = TravelLog(
        character_id=character.id,
        from_state_id=character.current_state_id,
        to_state_id=to_state_id,
        cost=cost,
        carrier_id=cid,
        mode=mode,
        carrier_name=carrier_name,
        started_at=now,
        arrives_at=arrives,
        activity_id=activity.id,
    )
    db.add(log)
    await db.flush()

    return {
        "from_state_id": log.from_state_id,
        "to_state_id": to_state_id,
        "to_state_name": dest.name,
        "carrier_id": cid,
        "carrier_name": carrier_name,
        "mode": mode.value if mode else None,
        "cost": cost,
        "minutes": minutes,
        "arrives_at": arrives.isoformat(),
        "cash": round(character.cash, 2),
        "is_traveling": True,
    }
