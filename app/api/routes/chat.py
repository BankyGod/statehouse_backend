from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import character_service, chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


class PostMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=500)


@router.get("/states/{state_id}/messages")
async def get_messages(
    state_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Auth required so public scraping is harder; any logged-in player may read
    _ = user
    return await chat_service.list_messages(
        db, state_id, limit=limit, before_id=before_id
    )


@router.post("/states/{state_id}/messages", status_code=201)
async def post_message(
    state_id: int,
    payload: PostMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await chat_service.post_message(db, character, state_id, payload.body)


@router.get("/home/messages")
async def home_messages(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await chat_service.list_messages(
        db, character.home_state_id, limit=limit
    )
