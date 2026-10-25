from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.character import Character
from app.models.housing import (
    HousingListing,
    Residence,
    ResidenceStatus,
    TenureType,
)
from app.services.character_service import ensure_can_act

RENT_PERIOD_DAYS = 7
EVICT_AFTER_MISSED = 2


def _apply_housing_bonus(character: Character, energy_bonus: int) -> None:
    base = character.base_max_energy or 100
    character.max_energy = base + energy_bonus
    if character.energy > character.max_energy:
        character.energy = character.max_energy


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
    if for_character is None:
        return [L for L in listings if not L.home_state_only]
    return [
        L
        for L in listings
        if (not L.home_state_only) or L.state_id == for_character.home_state_id
    ]


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
    character.active_residence_id = None
    character.is_homeless = True
    _apply_housing_bonus(character, 0)


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
    _apply_housing_bonus(character, listing.energy_bonus)
    await db.refresh(residence)
    return residence


async def rent_listing(
    db: AsyncSession, character: Character, listing_id: int
) -> Residence:
    ensure_can_act(character)
    listing = await db.get(HousingListing, listing_id)
    if listing is None or not listing.is_available:
        raise HTTPException(status_code=404, detail="Listing not found")

    if listing.home_state_only and listing.state_id != character.home_state_id:
        raise HTTPException(
            status_code=403, detail="This shelter is only for home-state residents"
        )

    # Must be in that state to move in (Torn-like: travel first)
    if character.current_state_id != listing.state_id:
        raise HTTPException(
            status_code=400, detail="Travel to that state before moving in"
        )

    # First week due upfront if rent > 0
    due = listing.weekly_rent
    if due > 0 and character.cash < due:
        raise HTTPException(status_code=400, detail="Need cash for first week's rent")

    await _end_active_residence(db, character, ResidenceStatus.LEFT)

    now = utcnow()
    if due > 0:
        character.cash -= due

    residence = Residence(
        character_id=character.id,
        listing_id=listing.id,
        state_id=listing.state_id,
        tenure=TenureType.RENT,
        status=ResidenceStatus.ACTIVE,
        weekly_rent=listing.weekly_rent,
        rent_due_at=now + timedelta(days=RENT_PERIOD_DAYS) if due >= 0 else None,
        missed_payments=0,
        started_at=now,
    )
    if listing.weekly_rent == 0:
        residence.rent_due_at = None

    db.add(residence)
    await db.flush()
    character.is_homeless = False
    character.active_residence_id = residence.id
    _apply_housing_bonus(character, listing.energy_bonus)
    await db.refresh(residence)
    return residence


async def buy_listing(
    db: AsyncSession, character: Character, listing_id: int
) -> Residence:
    ensure_can_act(character)
    listing = await db.get(HousingListing, listing_id)
    if listing is None or not listing.is_available:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.buy_price is None:
        raise HTTPException(status_code=400, detail="This listing is rent-only")
    if character.current_state_id != listing.state_id:
        raise HTTPException(
            status_code=400, detail="Travel to that state before buying"
        )
    if character.cash < listing.buy_price:
        raise HTTPException(status_code=400, detail="Insufficient cash to buy")

    await _end_active_residence(db, character, ResidenceStatus.LEFT)
    character.cash -= listing.buy_price
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
    _apply_housing_bonus(character, listing.energy_bonus)
    await db.refresh(residence)
    return residence


async def leave_residence(db: AsyncSession, character: Character) -> dict:
    ensure_can_act(character)
    current = await get_active_residence(db, character.id)
    if current is None:
        raise HTTPException(status_code=400, detail="No active residence")
    await _end_active_residence(db, character, ResidenceStatus.LEFT)
    await db.flush()
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
        character.cash -= amount
        paid = True
    elif character.bank_balance >= amount:
        character.bank_balance -= amount
        paid = True

    if paid:
        residence.missed_payments = 0
        residence.rent_due_at = now + timedelta(days=RENT_PERIOD_DAYS)
    else:
        residence.missed_payments += 1
        residence.rent_due_at = now + timedelta(days=RENT_PERIOD_DAYS)
        if residence.missed_payments >= EVICT_AFTER_MISSED:
            await _end_active_residence(db, character, ResidenceStatus.EVICTED)
            character.reputation = max(-100, character.reputation - 10)
