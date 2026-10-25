from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import (
    DmSendRequest,
    FactionCreateRequest,
    SocialNameRequest,
)
from app.services import character_service, social_service

router = APIRouter(prefix="/social", tags=["social"])


@router.get("/relations")
async def relations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.list_relations(db, character.id)


@router.post("/friends/request")
async def friend_request(
    payload: SocialNameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.request_friend(db, character, payload.display_name)


@router.post("/friends/{relation_id}/accept")
async def friend_accept(
    relation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.accept_friend(db, character, relation_id)


@router.post("/enemies")
async def add_enemy(
    payload: SocialNameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.add_enemy(db, character, payload.display_name)


@router.post("/attack")
async def attack(
    payload: SocialNameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.attack(db, character, payload.display_name)


@router.get("/messages")
async def messages(
    with_name: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.list_dms(
        db, character.id, with_name=with_name, limit=limit
    )


@router.post("/messages", status_code=201)
async def send_message(
    payload: DmSendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    msg = await social_service.send_dm(
        db, character, payload.to_display_name, payload.body
    )
    return {
        "id": msg.id,
        "to_character_id": msg.to_character_id,
        "body": msg.body,
        "posted_at": msg.posted_at,
    }


@router.get("/factions")
async def factions(db: AsyncSession = Depends(get_db)):
    return await social_service.list_factions(db)


@router.post("/factions", status_code=201)
async def create_faction(
    payload: FactionCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    f = await social_service.create_faction(
        db, character, payload.name, payload.tag, payload.description
    )
    return {"id": f.id, "name": f.name, "tag": f.tag}


@router.post("/factions/{faction_id}/join")
async def join_faction(
    faction_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await social_service.join_faction(db, character, faction_id)


@router.get("/events")
async def events(db: AsyncSession = Depends(get_db)):
    return await social_service.list_active_events(db)
