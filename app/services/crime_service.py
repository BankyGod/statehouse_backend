import random
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.activity import ActivityType
from app.models.character import Character
from app.models.crime import (
    CRIME_CATALOG,
    CrimeAttempt,
    CrimeType,
    CriminalRecord,
)
from app.models.state import State
from app.services.character_service import ensure_can_act, ensure_energy
from app.services.health_service import apply_damage
from app.services import inventory_service, notify_service


def list_catalog() -> list[dict]:
    return [{"crime_type": t, **meta} for t, meta in CRIME_CATALOG.items()]


def apply_nerve_regen(character: Character) -> int:
    settings = get_settings()
    now = utcnow()
    if character.nerve >= character.max_nerve:
        character.last_nerve_at = now
        return 0
    last = character.last_nerve_at or character.created_at or now
    if last.tzinfo is None:
        from datetime import timezone

        last = last.replace(tzinfo=timezone.utc)
    elapsed = (now - last).total_seconds()
    interval = settings.nerve_regen_minutes * 60
    if interval <= 0 or elapsed < interval:
        return 0
    gained = int(elapsed // interval)
    before = character.nerve
    character.nerve = min(character.max_nerve, character.nerve + gained)
    actual = character.nerve - before
    character.last_nerve_at = last + timedelta(seconds=actual * interval)
    if character.nerve >= character.max_nerve:
        character.last_nerve_at = now
    return actual


def ensure_nerve(character: Character, cost: int) -> None:
    if character.nerve < cost:
        raise HTTPException(status_code=400, detail="Not enough nerve")


def _effective_catch_rate(
    base: float, state_rate: float, heat: float, *, burglary_boost: bool = False
) -> float:
    heat_bonus = min(0.35, heat / 100.0)
    rate = (base * 0.55) + (state_rate * 0.45) + heat_bonus
    if burglary_boost:
        rate = max(0.10, rate - 0.12)
    return min(0.92, max(0.15, rate))


async def _steal_from_world(
    db: AsyncSession,
    thief: Character,
    state_id: int,
    desired: float,
) -> tuple[float, str]:
    """Take cash from a real victim (NPC/player) or shop in the state — not thin air."""
    from app.models.business import Business, BusinessStatus

    desired = round(max(0.0, float(desired)), 2)
    if desired <= 0:
        return 0.0, ""

    # Prefer a cash-holding person in the same state
    people = (
        await db.execute(
            select(Character)
            .where(
                Character.current_state_id == state_id,
                Character.id != thief.id,
                Character.cash >= 15,
                Character.is_jailed.is_(False),
            )
            .order_by(Character.cash.desc())
            .limit(12)
        )
    ).scalars().all()
    if people:
        victim = random.choice(people[: min(6, len(people))])
        take = round(min(desired, float(victim.cash) * 0.35, float(victim.cash)), 2)
        if take > 0:
            victim.cash = round(float(victim.cash) - take, 2)
            if not getattr(victim, "is_npc", False):
                await notify_service.push(
                    db,
                    victim.id,
                    "You were robbed",
                    body=f"${take:.2f} taken in {thief.display_name}'s crime.",
                    category="crime",
                )
            label = "NPC" if getattr(victim, "is_npc", False) else "citizen"
            return take, f"Stolen from {label} {victim.display_name}."

    shops = (
        await db.execute(
            select(Business)
            .where(
                Business.state_id == state_id,
                Business.status == BusinessStatus.ACTIVE,
                Business.cash_balance >= 25,
            )
            .order_by(Business.cash_balance.desc())
            .limit(8)
        )
    ).scalars().all()
    if shops:
        shop = random.choice(shops[: min(4, len(shops))])
        take = round(min(desired, float(shop.cash_balance) * 0.12), 2)
        if take > 0:
            shop.cash_balance = round(float(shop.cash_balance) - take, 2)
            await notify_service.push(
                db,
                shop.owner_id,
                f"{shop.name} was robbed",
                body=f"${take:.2f} missing from the till.",
                category="crime",
            )
            return take, f"Stolen from shop {shop.name}."

    # Fallback: street cash only (no victim found) — half payout
    return round(desired * 0.35, 2), "No rich target nearby — slim street take."


async def commit_crime(
    db: AsyncSession, character: Character, crime_type: CrimeType
) -> dict:
    ensure_can_act(character)
    apply_nerve_regen(character)
    meta = CRIME_CATALOG[crime_type]
    ensure_energy(character, meta["energy"])
    ensure_nerve(character, meta["nerve"])

    state = await db.get(State, character.current_state_id)
    if state is None:
        raise HTTPException(status_code=400, detail="Invalid current state")

    burglary_boost = (
        crime_type == CrimeType.BURGLARY and character.crime_boost_burglary
    )
    catch_chance = _effective_catch_rate(
        meta["base_catch_rate"],
        state.crime_catch_rate,
        character.heat,
        burglary_boost=burglary_boost,
    )
    if burglary_boost:
        character.crime_boost_burglary = False

    # Living catch pressure from player-held justice/customs posts
    from app.services import government_service

    catch_chance = await government_service.effective_crime_catch_rate(
        db, state, catch_chance
    )

    succeeded = random.random() < 0.72
    caught = random.random() < catch_chance

    character.energy -= meta["energy"]
    character.nerve -= meta["nerve"]
    character.last_energy_at = utcnow()
    character.last_nerve_at = utcnow()
    payout = 0.0
    fine = 0.0
    jail_hours = 0
    heat = float(meta["heat_gain"])
    loot = None

    victim_note = ""
    if succeeded and not caught:
        payout, victim_note = await _steal_from_world(
            db,
            character,
            state.id,
            float(random.uniform(meta["min_payout"], meta["max_payout"]))
            * max(0.4, 1.0 - (state.crime_catch_rate * 0.5)),
        )
        character.cash += payout
        character.heat += heat
        message = f"Got away with ${payout:.2f}. Heat +{heat:.0f}."
        if victim_note:
            message += f" {victim_note}"
        if meta.get("loot_chance") and random.random() < meta["loot_chance"]:
            loot = meta["loot_item"]
            if loot:
                await inventory_service.grant_loot(db, character.id, loot)
                message += f" Loot: {loot}."
    elif succeeded and caught:
        payout, victim_note = await _steal_from_world(
            db,
            character,
            state.id,
            float(random.uniform(meta["min_payout"], meta["max_payout"])) * 0.25,
        )
        character.cash += payout
        fine = float(meta["fine"])
        jail_hours = int(meta["jail_hours"])
        character.heat += heat * 1.5
        character.cash = max(0.0, character.cash - fine)
        character.is_jailed = True
        character.jail_until = utcnow() + timedelta(hours=jail_hours)
        message = (
            f"You scored ${payout:.2f} but security caught you. "
            f"Fine ${fine:.0f}, jail {jail_hours}h."
        )
        if victim_note:
            message += f" {victim_note}"
    elif not succeeded and caught:
        fine = float(meta["fine"]) * 0.5
        jail_hours = max(2, int(meta["jail_hours"] * 0.5))
        character.heat += heat
        character.cash = max(0.0, character.cash - fine)
        character.is_jailed = True
        character.jail_until = utcnow() + timedelta(hours=jail_hours)
        message = f"Failed and arrested. Fine ${fine:.0f}, jail {jail_hours}h."
    else:
        character.heat += heat * 0.5
        message = "Crime failed. You slipped away, but heat rose."

    injury = 0
    rough = (
        CrimeType.BURGLARY,
        CrimeType.SMUGGLING,
        CrimeType.ARMED_ROBBERY,
        CrimeType.CAR_THEFT,
    )
    if crime_type in rough and (caught or not succeeded):
        injury = apply_damage(
            character, random.randint(5, 22), condition="bruised"
        )
        if injury:
            message += f" Injured (-{injury} HP)."

    character.heat = min(100.0, character.heat)

    if fine > 0:
        from app.services import treasury_service
        from app.models.treasury import TreasuryTxType

        await treasury_service.collect_fee(
            db,
            fine,
            note=f"Crime fine — {meta['label']}",
            character_id=character.id,
            tx_type=TreasuryTxType.FINE,
        )

    attempt = CrimeAttempt(
        character_id=character.id,
        state_id=state.id,
        crime_type=crime_type,
        succeeded=succeeded,
        caught=caught,
        payout=payout,
        heat_applied=heat if succeeded or caught else heat * 0.5,
        fine_paid=fine,
        jail_hours=jail_hours,
        catch_chance_used=catch_chance,
        notes=message,
    )
    db.add(attempt)
    await db.flush()

    await notify_service.log_instant_activity(
        db,
        character.id,
        ActivityType.CRIME,
        meta["label"],
        description=message,
        cash_delta=payout - fine,
        energy_cost=meta["energy"],
    )

    if caught:
        record = CriminalRecord(
            character_id=character.id,
            crime_attempt_id=attempt.id,
            charge=meta["label"],
            sentence_hours=jail_hours,
            fine=fine,
            recorded_at=utcnow(),
        )
        db.add(record)
        summary = character.criminal_record_summary or ""
        line = f"{meta['label']} ({utcnow().date().isoformat()})"
        character.criminal_record_summary = (
            f"{summary}; {line}" if summary else line
        )[:500]
        await notify_service.push(
            db,
            character.id,
            "Arrested",
            body=message,
            category="jail",
        )

    await db.flush()

    return {
        "succeeded": succeeded,
        "caught": caught,
        "payout": round(payout, 2),
        "heat_applied": round(attempt.heat_applied, 2),
        "fine_paid": fine,
        "jail_hours": jail_hours,
        "catch_chance_used": round(catch_chance, 3),
        "message": message,
        "character_cash": round(character.cash, 2),
        "character_heat": round(character.heat, 2),
        "is_jailed": character.is_jailed,
        "health": character.health,
        "is_hospitalized": character.is_hospitalized,
        "injury": injury,
        "nerve": character.nerve,
        "loot": loot,
    }


async def history(
    db: AsyncSession, character_id: int, *, limit: int = 30
) -> list[dict]:
    result = await db.execute(
        select(CrimeAttempt)
        .where(CrimeAttempt.character_id == character_id)
        .order_by(CrimeAttempt.id.desc())
        .limit(limit)
    )
    rows = []
    for a in result.scalars().all():
        rows.append(
            {
                "id": a.id,
                "crime_type": a.crime_type,
                "succeeded": a.succeeded,
                "caught": a.caught,
                "payout": a.payout,
                "fine_paid": a.fine_paid,
                "jail_hours": a.jail_hours,
                "notes": a.notes,
                "created_at": a.created_at,
            }
        )
    return rows
