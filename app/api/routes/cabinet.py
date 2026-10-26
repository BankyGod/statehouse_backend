from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.cabinet import Portfolio
from app.models.user import User
from app.services import cabinet_service, character_service

router = APIRouter(prefix="/cabinet", tags=["cabinet"])


class AppointRequest(BaseModel):
    portfolio: str
    username: str = Field(min_length=1, max_length=64)
    character_id: int | None = Field(default=None, gt=0)


class PortfolioRequest(BaseModel):
    portfolio: str


@router.get("")
async def get_cabinet(db: AsyncSession = Depends(get_db)):
    return {"seats": await cabinet_service.list_cabinet(db)}


@router.get("/me")
async def my_seat(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {"seat": await cabinet_service.my_portfolio(db, character)}


@router.post("/appoint")
async def appoint(
    payload: AppointRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await cabinet_service.appoint(
        db,
        character,
        Portfolio(payload.portfolio),
        username=payload.username,
        character_id=payload.character_id,
    )


@router.post("/dismiss")
async def dismiss(
    payload: PortfolioRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await cabinet_service.dismiss(db, character, Portfolio(payload.portfolio))


@router.post("/resign")
async def resign(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await cabinet_service.resign(db, character)
