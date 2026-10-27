"""Real sector commerce — inventory, services, sales tax, economy hooks."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.business import Business, BusinessSector, BusinessStatus
from app.models.character import Character
from app.models.commerce import BusinessInventoryItem, BusinessSale
from app.models.treasury import TreasuryTxType
from app.seed.sector_catalog import (
    products_for,
    sector_mode,
    services_for,
)
from app.services.character_service import ensure_can_act


SALES_TAX_RATE = 0.05


def catalog_for_sector(sector: str) -> dict:
    return {
        "sector": sector,
        "mode": sector_mode(sector),
        "products": products_for(sector),
        "services": services_for(sector),
    }


async def _require_owner_business(
    db: AsyncSession, character: Character, business_id: int
) -> Business:
    biz = await db.get(Business, business_id)
    if biz is None or biz.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if biz.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business must be active")
    return biz


async def _require_active_business(db: AsyncSession, business_id: int) -> Business:
    biz = await db.get(Business, business_id)
    if biz is None or biz.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Business not found or inactive")
    return biz


async def list_inventory(db: AsyncSession, business_id: int) -> list[dict]:
    result = await db.execute(
        select(BusinessInventoryItem)
        .where(BusinessInventoryItem.business_id == business_id)
        .order_by(BusinessInventoryItem.sku)
    )
    return [
        {
            "id": i.id,
            "sku": i.sku,
            "label": i.label,
            "quantity": i.quantity,
            "unit_cost": i.unit_cost,
            "sell_price": i.sell_price,
            "is_listed": i.is_listed,
        }
        for i in result.scalars().all()
    ]


async def _get_or_create_item(
    db: AsyncSession, business: Business, sku: str, meta: dict
) -> BusinessInventoryItem:
    result = await db.execute(
        select(BusinessInventoryItem).where(
            BusinessInventoryItem.business_id == business.id,
            BusinessInventoryItem.sku == sku,
        )
    )
    item = result.scalar_one_or_none()
    if item:
        return item
    item = BusinessInventoryItem(
        business_id=business.id,
        sku=sku,
        label=meta["label"],
        quantity=0,
        unit_cost=float(meta["unit_cost"]),
        sell_price=float(meta["default_price"]),
        is_listed=True,
    )
    db.add(item)
    await db.flush()
    return item


async def restock_or_produce(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    sku: str,
    quantity: int,
) -> dict:
    ensure_can_act(character)
    if quantity <= 0 or quantity > 5000:
        raise HTTPException(status_code=400, detail="Invalid quantity")
    biz = await _require_owner_business(db, character, business_id)
    metas = {p["sku"]: p for p in products_for(biz.sector)}
    meta = metas.get(sku)
    if meta is None:
        raise HTTPException(status_code=400, detail="SKU not available for this sector")

    cost = round(float(meta["unit_cost"]) * quantity, 2)
    if biz.cash_balance < cost:
        raise HTTPException(
            status_code=400,
            detail=f"Company needs ${cost:.2f} cash to {meta['kind']} stock",
        )
    biz.cash_balance = round(biz.cash_balance - cost, 2)
    item = await _get_or_create_item(db, biz, sku, meta)
    item.unit_cost = float(meta["unit_cost"])
    item.quantity += quantity
    await db.flush()
    return {
        "business_id": biz.id,
        "sku": sku,
        "quantity": item.quantity,
        "spent": cost,
        "business_cash": biz.cash_balance,
        "action": meta["kind"],
    }


async def set_product_price(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    sku: str,
    sell_price: float,
    is_listed: bool = True,
) -> dict:
    ensure_can_act(character)
    if sell_price < 0.25:
        raise HTTPException(status_code=400, detail="Price too low")
    biz = await _require_owner_business(db, character, business_id)
    result = await db.execute(
        select(BusinessInventoryItem).where(
            BusinessInventoryItem.business_id == biz.id,
            BusinessInventoryItem.sku == sku,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Stock that SKU first")
    item.sell_price = round(float(sell_price), 2)
    item.is_listed = is_listed
    await db.flush()
    return {
        "sku": item.sku,
        "sell_price": item.sell_price,
        "is_listed": item.is_listed,
        "quantity": item.quantity,
    }


async def _credit_sale(
    db: AsyncSession,
    biz: Business,
    *,
    buyer: Character | None,
    kind: str,
    sku: str,
    label: str,
    quantity: int,
    gross: float,
) -> dict:
    from app.services import notify_service, treasury_service

    tax = round(gross * SALES_TAX_RATE, 2)
    net = round(gross - tax, 2)
    if tax > 0:
        await treasury_service.credit(
            db,
            tax,
            TreasuryTxType.FEE,
            note=f"Sales tax — {biz.name} / {sku}",
            character_id=buyer.id if buyer else None,
            business_id=biz.id,
        )
    biz.cash_balance = round(biz.cash_balance + net, 2)
    biz.lifetime_revenue = round(float(biz.lifetime_revenue or 0) + net, 2)
    db.add(
        BusinessSale(
            business_id=biz.id,
            buyer_character_id=buyer.id if buyer else None,
            kind=kind,
            sku=sku,
            label=label,
            quantity=quantity,
            gross=gross,
            tax=tax,
            net_to_business=net,
            posted_at=utcnow(),
        )
    )
    if buyer:
        await notify_service.push(
            db,
            biz.owner_id,
            f"Sale at {biz.name}",
            body=f"{label} ×{quantity} · +${net:.2f} (tax ${tax:.2f})",
            category="business",
            ref_type="business",
            ref_id=biz.id,
        )
    await db.flush()
    return {"gross": gross, "tax": tax, "net": net}


async def buy_product(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    sku: str,
    quantity: int = 1,
) -> dict:
    ensure_can_act(character)
    if quantity <= 0 or quantity > 100:
        raise HTTPException(status_code=400, detail="Invalid quantity")
    biz = await _require_active_business(db, business_id)
    result = await db.execute(
        select(BusinessInventoryItem).where(
            BusinessInventoryItem.business_id == biz.id,
            BusinessInventoryItem.sku == sku,
            BusinessInventoryItem.is_listed.is_(True),
        )
    )
    item = result.scalar_one_or_none()
    if item is None or item.quantity < quantity:
        raise HTTPException(status_code=400, detail="Not enough stock listed")

    gross = round(float(item.sell_price) * quantity, 2)
    if character.cash < gross:
        raise HTTPException(status_code=400, detail="Insufficient cash")
    character.cash = round(character.cash - gross, 2)
    item.quantity -= quantity
    pay = await _credit_sale(
        db,
        biz,
        buyer=character,
        kind="product",
        sku=sku,
        label=item.label,
        quantity=quantity,
        gross=gross,
    )
    metas = {p["sku"]: p for p in products_for(biz.sector)}
    meta = metas.get(sku) or {}
    effect_notes: list[str] = []
    effects = dict(meta.get("effects") or {})
    if effects:
        # Scale soft effects with quantity (cap)
        scaled = {
            k: (v * min(quantity, 3) if isinstance(v, (int, float)) else v)
            for k, v in effects.items()
        }
        effect_notes = await _apply_service_effects(db, character, scaled)
    return {
        "business_id": biz.id,
        "business_name": biz.name,
        "sku": sku,
        "quantity": quantity,
        "paid": gross,
        "tax": pay["tax"],
        "effects": effect_notes,
        "cash": character.cash,
    }


async def _apply_service_effects(
    db: AsyncSession, character: Character, effects: dict
) -> list[str]:
    notes: list[str] = []
    heal = int(effects.get("heal") or 0)
    if heal:
        character.health = min(
            int(character.max_health or 100),
            int(character.health or 0) + heal,
        )
        notes.append(f"+{heal} HP")
    energy = int(effects.get("energy") or 0)
    if energy:
        character.energy = min(
            int(character.max_energy or 100),
            int(character.energy or 0) + energy,
        )
        notes.append(f"+{energy} energy")
    happiness = int(effects.get("happiness") or 0)
    if happiness and hasattr(character, "happiness"):
        character.happiness = min(100, int(character.happiness or 50) + happiness)
        notes.append(f"+{happiness} happiness")
    heat_cut = float(effects.get("heat_cut") or 0)
    if heat_cut:
        character.heat = max(0.0, float(character.heat or 0) - heat_cut)
        notes.append(f"-{heat_cut:.0f} heat")
    rep = int(effects.get("reputation") or 0)
    if rep:
        character.reputation = min(100, int(character.reputation or 0) + rep)
        notes.append(f"+{rep} reputation")
    edu = int(effects.get("education_bump") or 0)
    if edu:
        # Soft bump via a micro enrollment completion mark on character notes/rep
        character.reputation = min(100, int(character.reputation or 0) + edu)
        notes.append("short course completed")
    age = float(effects.get("age_years") or 0)
    if age:
        character.age_years = float(character.age_years or 18) + age
        notes.append(f"+{age:.2f}y study")
    protect = int(effects.get("crime_protect_hours") or 0)
    if protect:
        from datetime import timedelta

        until = utcnow() + timedelta(hours=protect)
        # Stash on criminal_record_summary side channel avoided — use condition field lightly
        character.condition = f"guarded_until:{until.isoformat()}"
        notes.append(f"guarded {protect}h")
    power_days = int(effects.get("power_days") or 0)
    if power_days:
        from datetime import timedelta

        until = utcnow() + timedelta(days=power_days)
        prev = character.condition or ""
        character.condition = _stamp_condition(prev, "power_until", until.isoformat())
        notes.append(f"power {power_days}d")
    fuel_days = int(effects.get("fuel_days") or 0)
    if fuel_days:
        from datetime import timedelta

        until = utcnow() + timedelta(days=fuel_days)
        character.condition = _stamp_condition(
            character.condition or "", "fuel_until", until.isoformat()
        )
        notes.append(f"fuel {fuel_days}d")
    insure_days = int(effects.get("insure_days") or 0)
    if insure_days:
        from datetime import timedelta

        until = utcnow() + timedelta(days=insure_days)
        character.condition = _stamp_condition(
            character.condition or "", "insure_until", until.isoformat()
        )
        notes.append(f"insured {insure_days}d")
    await db.flush()
    return notes


def _stamp_condition(cond: str, key: str, value: str) -> str:
    parts = [p for p in (cond or "").split("|") if p and not p.startswith(f"{key}:")]
    parts.append(f"{key}:{value}")
    return "|".join(parts)


async def book_service(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    sku: str,
) -> dict:
    ensure_can_act(character)
    biz = await _require_active_business(db, business_id)
    metas = {s["sku"]: s for s in services_for(biz.sector)}
    meta = metas.get(sku)
    if meta is None:
        raise HTTPException(status_code=400, detail="Service not offered by this sector")

    price = float(meta["default_price"])
    opex = float(meta["unit_cost"])
    if character.cash < price:
        raise HTTPException(status_code=400, detail="Insufficient cash")
    # Company must cover opex from cash or from this payment — require liquidity for opex
    if biz.cash_balance + price < opex:
        raise HTTPException(
            status_code=400,
            detail="Company cannot deliver this service (cash too low)",
        )

    character.cash = round(character.cash - price, 2)
    # Opex leaves company after sale credits
    pay = await _credit_sale(
        db,
        biz,
        buyer=character,
        kind="service",
        sku=sku,
        label=meta["label"],
        quantity=1,
        gross=price,
    )
    biz.cash_balance = round(biz.cash_balance - opex, 2)
    biz.lifetime_wages = round(float(biz.lifetime_wages or 0) + opex, 2)  # opex proxy
    effect_notes = await _apply_service_effects(db, character, meta.get("effects") or {})

    # Logistics / energy economy side effects
    sector_val = biz.sector.value if hasattr(biz.sector, "value") else str(biz.sector)
    if sector_val in (
        BusinessSector.TRUCKING.value,
        BusinessSector.SHIPPING.value,
    ):
        from app.models.enterprise import EnterpriseKind, StateEnterprise
        from app.services import treasury_service

        # Port/rail share of private logistics
        kind = (
            EnterpriseKind.PORT
            if sector_val == BusinessSector.SHIPPING.value
            else EnterpriseKind.RAIL
        )
        ent = (
            await db.execute(select(StateEnterprise).where(StateEnterprise.kind == kind))
        ).scalar_one_or_none()
        fee = round(price * 0.08, 2)
        if ent and fee > 0:
            ent.cash_balance = round(float(ent.cash_balance or 0) + fee, 2)
            ent.lifetime_revenue = round(float(ent.lifetime_revenue or 0) + fee, 2)
        elif fee > 0:
            await treasury_service.credit(
                db, fee, TreasuryTxType.FEE, note="Logistics corridor fee"
            )

    # Construction crews improve the customer's home listing
    if sector_val == BusinessSector.CONSTRUCTION.value and sku in (
        "repair_crew",
        "fit_out",
    ):
        from app.models.housing import HousingListing, Residence, ResidenceStatus

        res = (
            await db.execute(
                select(Residence).where(
                    Residence.character_id == character.id,
                    Residence.status == ResidenceStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        if res:
            listing = await db.get(HousingListing, res.listing_id)
            if listing:
                bump = 2 if sku == "repair_crew" else 4
                listing.happiness_bonus = min(
                    25, int(listing.happiness_bonus or 0) + bump
                )
                listing.energy_bonus = min(20, int(listing.energy_bonus or 0) + 1)
                effect_notes.append(f"home +{bump} amenity")

    return {
        "business_id": biz.id,
        "business_name": biz.name,
        "sku": sku,
        "label": meta["label"],
        "paid": price,
        "tax": pay["tax"],
        "effects": effect_notes,
        "cash": character.cash,
        "energy": character.energy,
        "health": character.health,
    }


async def company_buy_wholesale(
    db: AsyncSession,
    character: Character,
    *,
    buyer_business_id: int,
    seller_business_id: int,
    sku: str,
    quantity: int = 1,
) -> dict:
    """B2B: one company spends cash to buy listed stock from another (supply chain)."""
    ensure_can_act(character)
    if quantity <= 0 or quantity > 500:
        raise HTTPException(status_code=400, detail="Invalid quantity")
    buyer = await _require_owner_business(db, character, buyer_business_id)
    seller = await _require_active_business(db, seller_business_id)
    if buyer.id == seller.id:
        raise HTTPException(status_code=400, detail="Cannot buy from yourself")
    result = await db.execute(
        select(BusinessInventoryItem).where(
            BusinessInventoryItem.business_id == seller.id,
            BusinessInventoryItem.sku == sku,
            BusinessInventoryItem.is_listed.is_(True),
        )
    )
    item = result.scalar_one_or_none()
    if item is None or item.quantity < quantity:
        raise HTTPException(status_code=400, detail="Seller stock unavailable")
    gross = round(float(item.sell_price) * quantity, 2)
    if buyer.cash_balance < gross:
        raise HTTPException(status_code=400, detail="Company cash too low")
    buyer.cash_balance = round(buyer.cash_balance - gross, 2)
    item.quantity -= quantity
    await _credit_sale(
        db,
        seller,
        buyer=None,
        kind="product",
        sku=sku,
        label=item.label,
        quantity=quantity,
        gross=gross,
    )
    # Restock buyer inventory under same sku label at landed cost
    meta = {
        "label": item.label,
        "unit_cost": item.sell_price,
        "default_price": round(float(item.sell_price) * 1.35, 2),
        "kind": "restock",
    }
    dest = await _get_or_create_item(db, buyer, sku, meta)
    dest.quantity += quantity
    dest.unit_cost = float(item.sell_price)
    await db.flush()
    return {
        "buyer_business_id": buyer.id,
        "seller_business_id": seller.id,
        "sku": sku,
        "quantity": quantity,
        "paid": gross,
        "buyer_cash": buyer.cash_balance,
        "stock_on_hand": dest.quantity,
    }


async def process_npc_marketplace_demand(db: AsyncSession) -> dict:
    """NPC households buy listed goods — sales tax + company revenue without players."""
    import random

    listed = list(
        (
            await db.execute(
                select(BusinessInventoryItem)
                .where(
                    BusinessInventoryItem.is_listed.is_(True),
                    BusinessInventoryItem.quantity > 0,
                )
                .limit(120)
            )
        ).scalars().all()
    )
    if not listed:
        return {"purchases": 0, "tax": 0.0}

    picks = random.sample(listed, k=min(8, len(listed)))
    purchases = 0
    tax_total = 0.0
    for item in picks:
        biz = await db.get(Business, item.business_id)
        if biz is None or biz.status != BusinessStatus.ACTIVE:
            continue
        qty = min(item.quantity, random.randint(1, 3))
        if qty <= 0:
            continue
        gross = round(float(item.sell_price) * qty, 2)
        item.quantity -= qty
        pay = await _credit_sale(
            db,
            biz,
            buyer=None,
            kind="product",
            sku=item.sku,
            label=item.label,
            quantity=qty,
            gross=gross,
        )
        purchases += 1
        tax_total += pay["tax"]
    await db.flush()
    return {"purchases": purchases, "tax": round(tax_total, 2)}


async def marketplace(
    db: AsyncSession,
    *,
    state_id: int | None = None,
    sector: str | None = None,
) -> dict:
    """Public listings players can buy/book."""
    stmt = select(Business).where(Business.status == BusinessStatus.ACTIVE)
    if state_id is not None:
        stmt = stmt.where(Business.state_id == state_id)
    if sector:
        stmt = stmt.where(Business.sector == sector)
    businesses = list((await db.execute(stmt.order_by(Business.id).limit(80))).scalars().all())

    products: list[dict] = []
    services: list[dict] = []
    for biz in businesses:
        mode = sector_mode(biz.sector)
        if mode in ("inventory", "mixed"):
            for item in await list_inventory(db, biz.id):
                if item["is_listed"] and item["quantity"] > 0:
                    products.append(
                        {
                            **item,
                            "business_id": biz.id,
                            "business_name": biz.name,
                            "sector": biz.sector,
                            "state_id": biz.state_id,
                        }
                    )
        if mode in ("services", "mixed") or services_for(biz.sector):
            for s in services_for(biz.sector):
                services.append(
                    {
                        "sku": s["sku"],
                        "label": s["label"],
                        "price": s["default_price"],
                        "business_id": biz.id,
                        "business_name": biz.name,
                        "sector": biz.sector,
                        "state_id": biz.state_id,
                        "effects": s.get("effects") or {},
                    }
                )
    return {"products": products, "services": services}


async def desk_summary(db: AsyncSession, business: Business) -> dict:
    return {
        "business_id": business.id,
        "sector": business.sector,
        "catalog": catalog_for_sector(business.sector),
        "inventory": await list_inventory(db, business.id),
        "mode": sector_mode(business.sector),
    }


async def charge_weekly_energy_bill(
    db: AsyncSession, character: Character
) -> dict | None:
    """Household energy bill → private energy cos or UAEGY treasury path."""
    from datetime import timedelta

    from app.models.enterprise import EnterpriseKind, StateEnterprise
    from app.services import treasury_service

    cond = character.condition or ""
    # Private power pack covers the week
    if "power_until:" in cond:
        try:
            raw = cond.split("power_until:")[-1].split("|")[0]
            until = datetime_from_isoformat(raw)
            if until > utcnow():
                return None
        except Exception:
            pass

    # Throttle: at most once per 7 days via last_energy bill stamp in condition
    if "energy_billed:" in cond:
        try:
            raw = cond.split("energy_billed:")[-1].split("|")[0]
            last = datetime_from_isoformat(raw)
            if (utcnow() - last).total_seconds() < 7 * 86400:
                return None
        except Exception:
            pass

    bill = 12.0
    paid = min(bill, float(character.cash or 0))
    if paid <= 0:
        return None
    character.cash = round(float(character.cash) - paid, 2)

    # Prefer a private energy company in the character's state
    private = (
        await db.execute(
            select(Business)
            .where(
                Business.sector == BusinessSector.ENERGY.value,
                Business.status == BusinessStatus.ACTIVE,
                Business.state_id == character.current_state_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if private:
        await _credit_sale(
            db,
            private,
            buyer=character,
            kind="service",
            sku="grid_bill",
            label="Weekly energy bill",
            quantity=1,
            gross=paid,
        )
    else:
        ent = (
            await db.execute(
                select(StateEnterprise).where(
                    StateEnterprise.kind == EnterpriseKind.POWER
                )
            )
        ).scalar_one_or_none()
        tax = round(paid * SALES_TAX_RATE, 2)
        net = round(paid - tax, 2)
        if tax > 0:
            await treasury_service.credit(
                db, tax, TreasuryTxType.FEE, note="Energy VAT", character_id=character.id
            )
        if ent:
            ent.cash_balance = round(float(ent.cash_balance or 0) + net, 2)
            ent.lifetime_revenue = round(float(ent.lifetime_revenue or 0) + net, 2)
        else:
            await treasury_service.credit(
                db, net, TreasuryTxType.FEE, note="Energy bill (UAEGY)", character_id=character.id
            )

    stamp = utcnow().isoformat()
    base = "|".join(
        p for p in cond.split("|") if p and not p.startswith("energy_billed:")
    )
    character.condition = f"{base}|energy_billed:{stamp}".strip("|")
    await db.flush()
    return {"paid": paid, "to": "private" if private else "uaegy"}


def datetime_from_isoformat(raw: str):
    from datetime import datetime

    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        from datetime import timezone

        dt = dt.replace(tzinfo=timezone.utc)
    return dt
