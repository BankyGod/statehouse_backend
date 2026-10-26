"""Housing market — government starter shelter + player real-estate companies."""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.business import Business, BusinessSector, BusinessStatus
from app.models.character import Character
from app.models.housing import (
    HousingKind,
    HousingListing,
    HousingOwnership,
    Residence,
    ResidenceStatus,
    TenureType,
)
from app.models.loan import Loan, LoanKind, LoanStatus
from app.models.treasury import TreasuryTxType
from app.services.character_service import ensure_can_act

RENT_PERIOD_DAYS = 7
EVICT_AFTER_MISSED = 2


def _apply_housing_bonus(
    character: Character,
    *,
    energy_bonus: int = 0,
    happiness_bonus: int = 0,
    energy_regen_bonus_minutes: int = 0,
) -> None:
    base = character.base_max_energy or 100
    character.max_energy = base + int(energy_bonus or 0)
    if character.energy > character.max_energy:
        character.energy = character.max_energy
    # Happiness from home quality (homeless → low baseline)
    character.happiness = max(0, min(100, int(happiness_bonus or 0)))
    character.housing_energy_regen_bonus = max(
        0, min(5, int(energy_regen_bonus_minutes or 0))
    )


def _clear_housing_bonus(character: Character) -> None:
    _apply_housing_bonus(
        character, energy_bonus=0, happiness_bonus=20, energy_regen_bonus_minutes=0
    )


def _listing_bonuses(listing: HousingListing) -> dict:
    return {
        "energy_bonus": int(listing.energy_bonus or 0),
        "happiness_bonus": int(getattr(listing, "happiness_bonus", 0) or 0),
        "energy_regen_bonus_minutes": int(
            getattr(listing, "energy_regen_bonus_minutes", 0) or 0
        ),
    }


async def _consume_unit(db: AsyncSession, listing: HousingListing) -> None:
    """Private stock: renting or buying takes one unit when tracked."""
    avail = getattr(listing, "units_available", None)
    if avail is None:
        return
    if avail <= 0:
        raise HTTPException(status_code=400, detail="No units left on this listing")
    listing.units_available = avail - 1
    if listing.units_available <= 0:
        listing.is_available = False
    await db.flush()


async def _release_rental_unit(db: AsyncSession, listing: HousingListing | None) -> None:
    if listing is None:
        return
    avail = getattr(listing, "units_available", None)
    total = getattr(listing, "units_total", None)
    if avail is None or total is None:
        return
    listing.units_available = min(total, avail + 1)
    if listing.units_available > 0:
        listing.is_available = True
    await db.flush()


async def _pay_landlord(
    db: AsyncSession,
    listing: HousingListing,
    amount: float,
    *,
    note: str,
    tenant_id: int,
) -> None:
    """Rent/sale proceeds → private real-estate company or national treasury."""
    amount = round(float(amount), 2)
    if amount <= 0:
        return
    if listing.owner_business_id:
        biz = await db.get(Business, listing.owner_business_id)
        if biz is not None and biz.status == BusinessStatus.ACTIVE:
            # Corporate tax on rental/sale income at collection
            from app.services import treasury_service

            split = await treasury_service.take_corporate_tax(
                db,
                amount,
                business_id=biz.id,
                note=f"Corporate tax — {note}",
            )
            biz.cash_balance = round(float(biz.cash_balance) + split["net"], 2)
            biz.lifetime_revenue = round(
                float(biz.lifetime_revenue or 0) + split["net"], 2
            )
            if biz.owner_id:
                from app.services import notify_service

                await notify_service.push(
                    db,
                    biz.owner_id,
                    f"{biz.name} received ${split['net']:.2f}",
                    body=note,
                    category="business",
                    ref_type="business",
                    ref_id=biz.id,
                )
            return
    from app.services import treasury_service

    await treasury_service.collect_fee(
        db,
        amount,
        note=note,
        character_id=tenant_id,
        tx_type=TreasuryTxType.FEE,
    )


async def list_listings(
    db: AsyncSession, state_id: int, *, for_character: Character | None = None
) -> list[HousingListing]:
    result = await db.execute(
        select(HousingListing).where(
            HousingListing.state_id == state_id,
            HousingListing.is_available.is_(True),
        )
    )
    listings = list(result.scalars().all())

    def _ok(L: HousingListing) -> bool:
        avail = getattr(L, "units_available", None)
        if avail is not None and avail <= 0:
            return False
        if for_character is None:
            return not L.home_state_only
        return (not L.home_state_only) or L.state_id == for_character.home_state_id

    return [L for L in listings if _ok(L)]


async def get_active_residence(
    db: AsyncSession, character_id: int
) -> Residence | None:
    result = await db.execute(
        select(Residence).where(
            Residence.character_id == character_id,
            Residence.status == ResidenceStatus.ACTIVE,
        )
    )
    return result.scalar_one_or_none()


async def _end_active_residence(
    db: AsyncSession, character: Character, status: ResidenceStatus
) -> None:
    current = await get_active_residence(db, character.id)
    if current:
        current.status = status
        current.ended_at = utcnow()
        # Free a rental unit back to the landlord's inventory
        if current.tenure == TenureType.RENT:
            listing = await db.get(HousingListing, current.listing_id)
            await _release_rental_unit(db, listing)
    character.active_residence_id = None
    character.is_homeless = True
    _clear_housing_bonus(character)


async def assign_starter_hostel(
    db: AsyncSession, character: Character
) -> Residence | None:
    """Free community hostel in home state — called on character create."""
    result = await db.execute(
        select(HousingListing).where(
            HousingListing.state_id == character.home_state_id,
            HousingListing.home_state_only.is_(True),
            HousingListing.is_available.is_(True),
        )
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        character.is_homeless = True
        return None

    now = utcnow()
    residence = Residence(
        character_id=character.id,
        listing_id=listing.id,
        state_id=listing.state_id,
        tenure=TenureType.RENT,
        status=ResidenceStatus.ACTIVE,
        weekly_rent=0.0,
        rent_due_at=None,
        missed_payments=0,
        started_at=now,
    )
    db.add(residence)
    await db.flush()
    character.is_homeless = False
    character.active_residence_id = residence.id
    bonuses = _listing_bonuses(listing)
    if bonuses["happiness_bonus"] <= 0 and listing.home_state_only:
        bonuses["happiness_bonus"] = 35
    _apply_housing_bonus(character, **bonuses)
    await db.refresh(residence)
    return residence


async def rent_listing(
    db: AsyncSession,
    character: Character,
    listing_id: int,
    *,
    skip_cash_check: bool = False,
) -> Residence:
    # Homeless players must still be able to secure shelter
    ensure_can_act(character, require_housing=False)
    listing = await db.get(HousingListing, listing_id)
    if listing is None or not listing.is_available:
        raise HTTPException(status_code=404, detail="Listing not found")

    if listing.home_state_only and listing.state_id != character.home_state_id:
        raise HTTPException(
            status_code=403, detail="This shelter is only for home-state residents"
        )

    if character.current_state_id != listing.state_id:
        raise HTTPException(
            status_code=400, detail="Travel to that state before moving in"
        )

    mode = getattr(listing, "offer_mode", None) or "both"
    if mode == "sale":
        raise HTTPException(status_code=400, detail="This listing is for sale only")
    if listing.weekly_rent is None or float(listing.weekly_rent) < 0:
        raise HTTPException(status_code=400, detail="Not a rental listing")

    due = float(listing.weekly_rent or 0)
    if due > 0 and not skip_cash_check and character.cash < due:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Need ${due:.2f} cash for first week's rent. "
                "If you are broke, request government housing assistance."
            ),
        )

    await _end_active_residence(db, character, ResidenceStatus.LEFT)
    await _consume_unit(db, listing)

    now = utcnow()
    if due > 0:
        if not skip_cash_check:
            character.cash = round(character.cash - due, 2)
        await _pay_landlord(
            db,
            listing,
            due,
            note=f"First week rent — {listing.title}",
            tenant_id=character.id,
        )

    residence = Residence(
        character_id=character.id,
        listing_id=listing.id,
        state_id=listing.state_id,
        tenure=TenureType.RENT,
        status=ResidenceStatus.ACTIVE,
        weekly_rent=listing.weekly_rent,
        rent_due_at=now + timedelta(days=RENT_PERIOD_DAYS) if due > 0 else None,
        missed_payments=0,
        started_at=now,
    )
    if listing.weekly_rent == 0:
        residence.rent_due_at = None

    db.add(residence)
    await db.flush()
    character.is_homeless = False
    character.active_residence_id = residence.id
    _apply_housing_bonus(character, **_listing_bonuses(listing))
    await db.refresh(residence)
    return residence


async def buy_listing(
    db: AsyncSession, character: Character, listing_id: int
) -> Residence:
    ensure_can_act(character, require_housing=False)
    listing = await db.get(HousingListing, listing_id)
    if listing is None or not listing.is_available:
        raise HTTPException(status_code=404, detail="Listing not found")
    mode = getattr(listing, "offer_mode", None) or "both"
    if mode == "rent":
        raise HTTPException(status_code=400, detail="This listing is rent-only")
    if listing.buy_price is None or float(listing.buy_price) <= 0:
        raise HTTPException(status_code=400, detail="This listing is rent-only")
    if character.current_state_id != listing.state_id:
        raise HTTPException(
            status_code=400, detail="Travel to that state before buying"
        )
    if character.cash < listing.buy_price:
        raise HTTPException(status_code=400, detail="Insufficient cash to buy")

    await _end_active_residence(db, character, ResidenceStatus.LEFT)
    await _consume_unit(db, listing)
    price = float(listing.buy_price)
    character.cash = round(character.cash - price, 2)
    await _pay_landlord(
        db,
        listing,
        price,
        note=f"Property sale — {listing.title}",
        tenant_id=character.id,
    )

    now = utcnow()
    residence = Residence(
        character_id=character.id,
        listing_id=listing.id,
        state_id=listing.state_id,
        tenure=TenureType.OWN,
        status=ResidenceStatus.ACTIVE,
        weekly_rent=0.0,
        rent_due_at=None,
        missed_payments=0,
        started_at=now,
    )
    db.add(residence)
    await db.flush()
    character.is_homeless = False
    character.active_residence_id = residence.id
    character.reputation += 5
    _apply_housing_bonus(character, **_listing_bonuses(listing))
    await db.refresh(residence)
    return residence


async def leave_residence(db: AsyncSession, character: Character) -> dict:
    ensure_can_act(character, require_housing=False)
    current = await get_active_residence(db, character.id)
    if current is None:
        raise HTTPException(status_code=400, detail="No active residence")
    await _end_active_residence(db, character, ResidenceStatus.LEFT)
    await db.flush()
    from app.services import notify_service

    await notify_service.push(
        db,
        character.id,
        "You are homeless",
        body="Secure housing or request government housing assistance to keep playing.",
        category="housing",
    )
    return {"is_homeless": True, "message": "You left your residence"}


async def process_rent(db: AsyncSession, character: Character) -> None:
    """Auto-collect due rent on tick; evict after repeated misses."""
    residence = await get_active_residence(db, character.id)
    if residence is None or residence.tenure != TenureType.RENT:
        return
    if residence.weekly_rent <= 0 or residence.rent_due_at is None:
        return

    due_at = residence.rent_due_at
    if due_at.tzinfo is None:
        from datetime import timezone

        due_at = due_at.replace(tzinfo=timezone.utc)

    now = utcnow()
    if due_at > now:
        return

    amount = residence.weekly_rent
    paid = False
    if character.cash >= amount:
        character.cash = round(character.cash - amount, 2)
        paid = True
    elif character.bank_balance >= amount:
        character.bank_balance = round(character.bank_balance - amount, 2)
        paid = True

    listing = await db.get(HousingListing, residence.listing_id)
    if paid:
        residence.missed_payments = 0
        residence.rent_due_at = now + timedelta(days=RENT_PERIOD_DAYS)
        if listing:
            await _pay_landlord(
                db,
                listing,
                amount,
                note=f"Weekly rent — {listing.title}",
                tenant_id=character.id,
            )
    else:
        residence.missed_payments += 1
        residence.rent_due_at = now + timedelta(days=RENT_PERIOD_DAYS)
        from app.services import notify_service

        await notify_service.push(
            db,
            character.id,
            "Rent missed",
            body=f"Could not pay ${amount:.2f}. Missed {residence.missed_payments}/{EVICT_AFTER_MISSED}.",
            category="housing",
        )
        if residence.missed_payments >= EVICT_AFTER_MISSED:
            await _end_active_residence(db, character, ResidenceStatus.EVICTED)
            character.reputation = max(-100, character.reputation - 10)
            await notify_service.push(
                db,
                character.id,
                "Evicted",
                body="You lost your home. Request government housing assistance or rent again.",
                category="housing",
            )


async def _require_real_estate_business(
    db: AsyncSession, character: Character, business_id: int
) -> Business:
    ensure_can_act(character)
    biz = await db.get(Business, business_id)
    if biz is None or biz.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if biz.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business must be active")
    sector = biz.sector.value if hasattr(biz.sector, "value") else str(biz.sector)
    if sector != BusinessSector.REAL_ESTATE.value:
        raise HTTPException(
            status_code=400,
            detail="Only a real estate company can manage housing listings",
        )
    return biz


async def create_private_listing(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    property_type: str,
    units: int = 1,
    offer_mode: str = "both",
    title: str | None = None,
    description: str | None = None,
    weekly_rent: float | None = None,
    buy_price: float | None = None,
) -> HousingListing:
    """
    Company buys `units` of a property type (pays acquisition from company cash),
    then lists them for rent and/or sale at the prices you set.
    """
    from app.seed.property_catalog import property_type_by_slug

    biz = await _require_real_estate_business(db, character, business_id)
    meta = property_type_by_slug(property_type)
    if meta is None:
        raise HTTPException(status_code=400, detail="Unknown property type")

    units = int(units)
    if units < 1 or units > 50:
        raise HTTPException(status_code=400, detail="Units must be between 1 and 50")

    mode = (offer_mode or "both").strip().lower()
    if mode not in ("rent", "sale", "both"):
        raise HTTPException(
            status_code=400, detail="offer_mode must be rent, sale, or both"
        )

    rent = (
        round(float(weekly_rent), 2)
        if weekly_rent is not None
        else float(meta["suggested_weekly_rent"])
    )
    sale = (
        round(float(buy_price), 2)
        if buy_price is not None
        else float(meta["suggested_buy_price"])
    )

    if mode == "rent":
        sale = None
        if rent <= 0:
            raise HTTPException(status_code=400, detail="Weekly rent must be positive")
    elif mode == "sale":
        rent = 0.0
        if sale is None or sale <= 0:
            raise HTTPException(status_code=400, detail="Sale price must be positive")
    else:
        if rent < 0:
            raise HTTPException(status_code=400, detail="Rent cannot be negative")
        if sale is None or sale <= 0:
            raise HTTPException(
                status_code=400, detail="Sale price required for both mode"
            )

    each = float(meta["acquisition_cost"])
    total_cost = round(each * units, 2)
    if float(biz.cash_balance) < total_cost:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Company needs ${total_cost:.2f} to acquire {units}× {meta['label']} "
                f"(${each:.0f} each). Deposit into the company treasury first."
            ),
        )

    biz.cash_balance = round(float(biz.cash_balance) - total_cost, 2)
    try:
        kind_enum = HousingKind(meta["kind"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid housing kind") from exc

    default_title = f"{meta['label']} — {biz.name}"
    listing = HousingListing(
        state_id=biz.state_id,
        title=(title or default_title).strip()[:128],
        kind=kind_enum,
        description=(
            description
            or f"{meta['blurb']} Listed by {biz.name}."
        )[:2000],
        weekly_rent=rent,
        buy_price=sale,
        energy_bonus=int(meta["energy_bonus"]),
        home_state_only=False,
        is_available=True,
        ownership=HousingOwnership.PRIVATE.value,
        owner_business_id=biz.id,
        property_type_slug=meta["slug"],
        offer_mode=mode,
        acquisition_cost_each=each,
        units_total=units,
        units_available=units,
        happiness_bonus=int(meta["happiness_bonus"]),
        energy_regen_bonus_minutes=int(meta["energy_regen_bonus_minutes"]),
    )
    db.add(listing)
    await db.flush()
    await db.refresh(listing)

    from app.services import notify_service

    await notify_service.push(
        db,
        character.id,
        f"{biz.name} acquired property stock",
        body=(
            f"{units}× {meta['label']} for ${total_cost:.0f}. "
            f"Mode: {mode}. Cash left ${biz.cash_balance:.2f}."
        ),
        category="business",
        ref_type="business",
        ref_id=biz.id,
    )
    return listing


def property_catalog() -> dict:
    from app.seed.property_catalog import PROPERTY_TYPE_CATALOG

    return {
        "property_types": PROPERTY_TYPE_CATALOG,
        "offer_modes": [
            {"value": "rent", "label": "Rent only"},
            {"value": "sale", "label": "Sale only"},
            {"value": "both", "label": "Rent or buy"},
        ],
        "max_units_per_listing": 50,
        "note": (
            "Company pays acquisition_cost × units from company cash to stock the listing. "
            "You then set rent and/or sale price per unit. Bigger homes give more happiness "
            "and faster energy regen for tenants."
        ),
    }


async def update_listing_prices(
    db: AsyncSession,
    character: Character,
    business_id: int,
    listing_id: int,
    *,
    weekly_rent: float | None = None,
    buy_price: float | None = None,
    is_available: bool | None = None,
    offer_mode: str | None = None,
) -> HousingListing:
    biz = await _require_real_estate_business(db, character, business_id)
    listing = await db.get(HousingListing, listing_id)
    if listing is None or listing.owner_business_id != biz.id:
        raise HTTPException(status_code=404, detail="Listing not found for this company")
    if weekly_rent is not None:
        weekly_rent = round(float(weekly_rent), 2)
        if weekly_rent < 0:
            raise HTTPException(status_code=400, detail="Rent cannot be negative")
        listing.weekly_rent = weekly_rent
    if buy_price is not None:
        if buy_price <= 0:
            listing.buy_price = None
        else:
            listing.buy_price = round(float(buy_price), 2)
    if offer_mode is not None:
        mode = offer_mode.strip().lower()
        if mode not in ("rent", "sale", "both"):
            raise HTTPException(status_code=400, detail="Invalid offer_mode")
        listing.offer_mode = mode
        if mode == "rent":
            listing.buy_price = None
        if mode == "sale":
            listing.weekly_rent = 0.0
    if is_available is not None:
        listing.is_available = bool(is_available)
    await db.flush()
    await db.refresh(listing)
    return listing


async def list_business_listings(
    db: AsyncSession, character: Character, business_id: int
) -> list[HousingListing]:
    await _require_real_estate_business(db, character, business_id)
    result = await db.execute(
        select(HousingListing).where(HousingListing.owner_business_id == business_id)
    )
    return list(result.scalars().all())


async def request_housing_assistance(
    db: AsyncSession,
    character: Character,
    *,
    listing_id: int | None = None,
) -> dict:
    """
    If homeless / broke: government messages you and funds a housing welfare loan
    so you can move into basic shelter. Repaid gradually from future wages.
    """
    ensure_can_act(character, require_housing=False)
    settings = get_settings()
    from app.services import notify_service, treasury_service

    # Prefer free government hostel in home state if available and character is there
    listing: HousingListing | None = None
    if listing_id is not None:
        listing = await db.get(HousingListing, listing_id)
        if listing is None or not listing.is_available:
            raise HTTPException(status_code=404, detail="Listing not found")
    else:
        # Cheapest available option in current state (gov hostel first)
        result = await db.execute(
            select(HousingListing)
            .where(
                HousingListing.state_id == character.current_state_id,
                HousingListing.is_available.is_(True),
            )
            .order_by(HousingListing.weekly_rent.asc(), HousingListing.id.asc())
        )
        candidates = list(result.scalars().all())
        for L in candidates:
            if L.home_state_only and L.state_id != character.home_state_id:
                continue
            listing = L
            break
        if listing is None and character.current_state_id != character.home_state_id:
            # Fall back: free home-state hostel requires travel first
            raise HTTPException(
                status_code=400,
                detail="No listings here. Travel home for the free community hostel, or pick a listing_id.",
            )

    if listing is None:
        raise HTTPException(status_code=404, detail="No housing available")

    due = float(listing.weekly_rent or 0)
    loan_issued = None
    funded = 0.0

    if due > 0 and character.cash < due:
        # Existing active welfare loan?
        existing = await db.execute(
            select(Loan).where(
                Loan.character_id == character.id,
                Loan.status == LoanStatus.ACTIVE,
                Loan.loan_kind == LoanKind.HOUSING_WELFARE.value,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="You already have an active housing welfare loan — pay it down first",
            )

        need = round(due - character.cash, 2)
        need = min(need, settings.housing_welfare_max)
        if need <= 0:
            need = due

        await notify_service.push(
            db,
            character.id,
            "Message from the Government",
            body=(
                f"You cannot meet basic housing needs. United Amir will loan you "
                f"${need:.2f} for shelter. It will be collected gradually from your wages."
            ),
            category="government",
        )

        # Fund from treasury → character cash (restricted use: we immediately rent)
        paid = await treasury_service.debit(
            db,
            need,
            TreasuryTxType.TRANSFER,
            note=f"Housing welfare loan — {character.display_name}",
            character_id=character.id,
            allow_overdraft=True,
        )
        character.cash = round(float(character.cash) + paid, 2)
        funded = paid
        total_due = round(paid * (1 + settings.housing_welfare_interest), 2)
        now = utcnow()
        loan = Loan(
            character_id=character.id,
            principal=paid,
            remaining=total_due,
            interest_rate=settings.housing_welfare_interest,
            status=LoanStatus.ACTIVE,
            issued_at=now,
            due_at=now + timedelta(days=settings.housing_welfare_term_days),
            loan_kind=LoanKind.HOUSING_WELFARE.value,
            auto_repay=True,
            repay_pct_of_gross=settings.housing_welfare_repay_pct,
        )
        db.add(loan)
        await db.flush()
        loan_issued = loan.id

    if character.current_state_id != listing.state_id:
        raise HTTPException(
            status_code=400,
            detail="Travel to that state before claiming housing assistance",
        )

    residence = await rent_listing(
        db, character, listing.id, skip_cash_check=False
    )
    return {
        "assisted": True,
        "residence_id": residence.id,
        "listing_id": listing.id,
        "listing_title": listing.title,
        "weekly_rent": residence.weekly_rent,
        "loan_id": loan_issued,
        "loan_funded": funded,
        "message": (
            "You are housed. Work shifts — a share of each paycheck repays your welfare loan."
            if loan_issued
            else "You are housed."
        ),
    }


async def backfill_government_ownership(db: AsyncSession) -> int:
    """Mark existing unowned listings as government stock."""
    result = await db.execute(select(HousingListing))
    n = 0
    for listing in result.scalars().all():
        if not listing.owner_business_id and listing.ownership != HousingOwnership.GOVERNMENT.value:
            listing.ownership = HousingOwnership.GOVERNMENT.value
            n += 1
        elif not listing.ownership:
            listing.ownership = HousingOwnership.GOVERNMENT.value
            n += 1
    if n:
        await db.flush()
    return n
