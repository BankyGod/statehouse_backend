from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import character_service, notify_service

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/me")
async def my_activities(
    limit: int = Query(default=40, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await notify_service.list_activities(db, character.id, limit=limit)


@router.get("/notifications")
async def my_notifications(
    limit: int = Query(default=40, ge=1, le=100),
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await notify_service.list_notifications(
        db, character.id, limit=limit, unread_only=unread_only
    )


@router.post("/notifications/read")
async def mark_notifications_read(
    notification_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    count = await notify_service.mark_read(db, character.id, notification_id)
    return {"marked": count}
