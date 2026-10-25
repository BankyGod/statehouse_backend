from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.character import CharacterCreate, CharacterOut, HomeStateResetRequest
from app.services import bank_service, character_service

router = APIRouter(prefix="/characters", tags=["characters"])


@router.post("", response_model=CharacterOut, status_code=201)
async def create_character(
    payload: CharacterCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await character_service.create_character(db, user, payload)


@router.get("/me", response_model=CharacterOut)
async def get_my_character(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # get_character_for_user already runs tick (regen, travel, education, business)
    character = await character_service.get_character_for_user(db, user)
    await bank_service.mark_overdue_defaults(db, character)
    await db.refresh(character)
    return character


@router.post("/me/home-state/reset", response_model=CharacterOut)
async def reset_home_state(
    payload: HomeStateResetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await character_service.reset_home_state(
        db, character, payload.new_home_state_id
    )
