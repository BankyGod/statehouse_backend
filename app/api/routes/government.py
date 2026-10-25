from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import character_service, government_service

router = APIRouter(prefix="/government", tags=["government"])


class ApplyRequest(BaseModel):
    post_id: int = Field(gt=0)


@router.get("/posts")
async def list_posts(
    state_id: int | None = Query(default=None),
    open_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    return {
        "posts": await government_service.list_posts(
            db, state_id=state_id, open_only=open_only
        )
    }


@router.get("/me")
async def my_post(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {"post": await government_service.my_post(db, character.id)}


@router.post("/apply")
async def apply(
    payload: ApplyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await government_service.apply_for_post(db, character, payload.post_id)


@router.post("/resign")
async def resign(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await government_service.resign_post(db, character)
