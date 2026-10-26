from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.business import Business, BusinessEntityType
from app.models.user import User
from app.schemas.life import (
    BusinessCashRequest,
    BusinessCreate,
    BusinessOut,
    EmployeeOut,
    EmployeeUpdateRequest,
    HireNpcRequest,
    HirePlayerRequest,
    HousingListingOut,
    RealEstateListingCreate,
    RealEstateListingUpdate,
)
from app.services import (
    business_service,
    character_service,
    employee_service,
    housing_service,
    performance_service,
)

router = APIRouter(prefix="/businesses", tags=["businesses"])


async def _to_out(db: AsyncSession, business: Business) -> BusinessOut:
    count = await employee_service.employee_count(db, business.id)
    return BusinessOut(
        id=business.id,
        name=business.name,
        sector=business.sector,
        entity_type=getattr(business, "entity_type", None)
        or BusinessEntityType.SOLE_TRADER.value,
        state_id=business.state_id,
        status=business.status.value if hasattr(business.status, "value") else str(business.status),
        cash_balance=business.cash_balance,
        local_address=business.local_address,
        is_home_state=business.is_home_state,
        registered_at=business.registered_at,
        registration_completes_at=business.registration_completes_at,
        employee_count=count,
        description=business.description,
        is_public=business.is_public,
        lifetime_revenue=getattr(business, "lifetime_revenue", 0.0) or 0.0,
        lifetime_wages=getattr(business, "lifetime_wages", 0.0) or 0.0,
    )


@router.get("/catalog")
async def business_catalog():
    return business_service.registration_catalog()


@router.get("/property-catalog")
async def property_catalog():
    """Real-estate inventory types (acquisition cost, bonuses, suggested prices)."""
    return housing_service.property_catalog()


@router.get("/preview")
async def business_preview(
    state_id: int = Query(...),
    entity_type: str = Query(default="sole_trader"),
    starting_capital: float = Query(default=0, ge=0, le=50000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    try:
        et = BusinessEntityType(entity_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid business type") from exc
    return await business_service.registration_preview(
        db,
        character,
        state_id=state_id,
        entity_type=et,
        starting_capital=starting_capital,
    )


@router.post("", response_model=BusinessOut, status_code=201)
async def create_business(
    payload: BusinessCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    await business_service.activate_due_businesses(db, character)
    business = await business_service.register_business(
        db,
        character,
        name=payload.name,
        sector=payload.sector,
        state_id=payload.state_id,
        local_address=payload.local_address,
        description=payload.description,
        entity_type=payload.entity_type,
        starting_capital=payload.starting_capital,
    )
    return await _to_out(db, business)


@router.get("/me", response_model=list[BusinessOut])
async def my_businesses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    await business_service.activate_due_businesses(db, character)
    result = await db.execute(
        select(Business).where(Business.owner_id == character.id)
    )
    businesses = list(result.scalars().all())
    return [await _to_out(db, b) for b in businesses]


@router.get("/{business_id}/employees", response_model=list[EmployeeOut])
async def list_business_employees(
    business_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    return await employee_service.list_employees(db, business_id)


@router.post(
    "/{business_id}/employees/hire",
    response_model=EmployeeOut,
    status_code=201,
)
async def hire_npc_employee(
    business_id: int,
    payload: HireNpcRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.hire_npc(
        db,
        character,
        business_id,
        role=payload.role,
        display_name=payload.display_name,
    )


@router.post(
    "/{business_id}/employees/hire-player",
    status_code=201,
)
async def hire_player_employee(
    business_id: int,
    payload: HirePlayerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.hire_player(
        db,
        character,
        business_id,
        display_name=payload.display_name,
        character_id=payload.character_id,
        role=payload.role,
        wage_per_week=payload.wage_per_week,
        message=payload.message,
    )


@router.get("/{business_id}/invites")
async def list_business_invites(
    business_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {
        "invites": await employee_service.list_outgoing_invites(
            db, character, business_id
        )
    }


@router.post("/{business_id}/invites/{invite_id}/cancel")
async def cancel_business_invite(
    business_id: int,
    invite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.cancel_invite(db, character, business_id, invite_id)


@router.patch(
    "/{business_id}/employees/{employee_id}",
    response_model=EmployeeOut,
)
async def update_business_employee(
    business_id: int,
    employee_id: int,
    payload: EmployeeUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.update_employee(
        db,
        character,
        business_id,
        employee_id,
        role=payload.role,
        wage_per_week=payload.wage_per_week,
        display_name=payload.display_name,
    )


@router.delete("/{business_id}/employees/{employee_id}")
async def fire_business_employee(
    business_id: int,
    employee_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.fire_employee(
        db, character, business_id, employee_id
    )


@router.get("/{business_id}/performance")
async def business_performance(
    business_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner dashboard: ops metrics, IPO checklist, and real stock price history."""
    character = await character_service.get_character_for_user(db, user)
    return await performance_service.performance_dashboard(db, character, business_id)


@router.post("/{business_id}/deposit")
async def deposit_cash(
    business_id: int,
    payload: BusinessCashRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await business_service.deposit(db, character, business_id, payload.amount)


@router.post("/{business_id}/withdraw")
async def withdraw_cash(
    business_id: int,
    payload: BusinessCashRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await business_service.withdraw(db, character, business_id, payload.amount)


@router.get("/{business_id}/listings", response_model=list[HousingListingOut])
async def business_housing_listings(
    business_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listings managed by a real estate company."""
    character = await character_service.get_character_for_user(db, user)
    return await housing_service.list_business_listings(db, character, business_id)


@router.post(
    "/{business_id}/listings",
    response_model=HousingListingOut,
    status_code=201,
)
async def create_business_listing(
    business_id: int,
    payload: RealEstateListingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    listing = await housing_service.create_private_listing(
        db,
        character,
        business_id,
        state_id=payload.state_id,
        property_type=payload.property_type,
        units=payload.units,
        offer_mode=payload.offer_mode,
        title=payload.title,
        description=payload.description,
        weekly_rent=payload.weekly_rent,
        buy_price=payload.buy_price,
    )
    await db.commit()
    await db.refresh(listing)
    return listing


@router.patch("/{business_id}/listings/{listing_id}", response_model=HousingListingOut)
async def update_business_listing(
    business_id: int,
    listing_id: int,
    payload: RealEstateListingUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await housing_service.update_listing_prices(
        db,
        character,
        business_id,
        listing_id,
        weekly_rent=payload.weekly_rent,
        buy_price=payload.buy_price,
        is_available=payload.is_available,
        offer_mode=payload.offer_mode,
    )
