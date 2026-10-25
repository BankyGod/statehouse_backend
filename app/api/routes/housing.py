from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import HousingListingOut, HousingMoveRequest, ResidenceOut
from app.services import character_service, housing_service

router = APIRouter(prefix="/housing", tags=["housing"])


@router.get("/listings", response_model=list[HousingListingOut])
async def listings(
    state_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    target = state_id or character.current_state_id
    return await housing_service.list_listings(db, target, for_character=character)


@router.get("/me", response_model=ResidenceOut | None)
async def my_residence(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await housing_service.get_active_residence(db, character.id)


@router.post("/rent", response_model=ResidenceOut, status_code=201)
async def rent(
    payload: HousingMoveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await housing_service.rent_listing(db, character, payload.listing_id)


@router.post("/buy", response_model=ResidenceOut, status_code=201)
async def buy(
    payload: HousingMoveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await housing_service.buy_listing(db, character, payload.listing_id)


@router.post("/leave")
async def leave(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await housing_service.leave_residence(db, character)
