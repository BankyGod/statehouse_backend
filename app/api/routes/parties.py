from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import character_service, party_service

router = APIRouter(prefix="/parties", tags=["parties"])


class JoinPartyRequest(BaseModel):
    party_id: int = Field(gt=0)


@router.get("")
async def list_parties(db: AsyncSession = Depends(get_db)):
    return {"parties": await party_service.list_parties(db)}


@router.get("/me")
async def my_party(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {"membership": await party_service.my_membership(db, character.id)}


@router.post("/join")
async def join_party(
    payload: JoinPartyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await party_service.join_party(db, character, payload.party_id)


@router.post("/leave")
async def leave_party(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await party_service.leave_party(db, character)
