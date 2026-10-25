from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import GymTrainRequest
from app.services import character_service, gym_service

router = APIRouter(prefix="/gym", tags=["gym"])


@router.get("/catalog")
async def catalog():
    return gym_service.catalog()


@router.post("/train")
async def train(
    payload: GymTrainRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await gym_service.train(db, character, payload.stat)
