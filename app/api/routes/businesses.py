from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.business import Business
from app.models.user import User
from app.schemas.life import (
    BusinessCashRequest,
    BusinessCreate,
    BusinessOut,
    EmployeeOut,
    HireNpcRequest,
    HirePlayerRequest,
)
from app.services import business_service, character_service, employee_service

router = APIRouter(prefix="/businesses", tags=["businesses"])


async def _to_out(db: AsyncSession, business: Business) -> BusinessOut:
    count = await employee_service.employee_count(db, business.id)
    return BusinessOut(
        id=business.id,
        name=business.name,
        sector=business.sector,
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
    response_model=EmployeeOut,
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
        role=payload.role,
        wage_per_week=payload.wage_per_week,
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
