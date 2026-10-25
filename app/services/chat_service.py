from datetime import timedelta
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.models.chat import ChatMessage
from app.models.state import State
from app.services.character_service import ensure_can_act

# Light spam / abuse filter (not a full moderation system)
_BLOCKED = re.compile(r"(https?://|www\.|\.exe\b)", re.IGNORECASE)


async def list_messages(
    db: AsyncSession, state_id: int, *, limit: int = 50, before_id: int | None = None
) -> list[dict]:
    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    limit = min(max(limit, 1), 100)
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.state_id == state_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(ChatMessage.id < before_id)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()  # chronological for UI
    return [
        {
            "id": m.id,
            "state_id": m.state_id,
            "character_id": m.character_id,
            "display_name": m.display_name,
            "body": m.body,
            "posted_at": m.posted_at,
        }
        for m in rows
    ]


async def post_message(
    db: AsyncSession, character: Character, state_id: int, body: str
) -> dict:
    ensure_can_act(character)
    settings = get_settings()

    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    # Residents always; visitors only if currently in the state
    if (
        character.home_state_id != state_id
        and character.current_state_id != state_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only chat in your home state or the state you are in",
        )

    text = (body or "").strip()
    if len(text) < 1:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(text) > settings.chat_max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long (max {settings.chat_max_length})",
        )
    if _BLOCKED.search(text):
        raise HTTPException(status_code=400, detail="Message contains blocked content")

    # Rate limit
    since = utcnow() - timedelta(seconds=settings.chat_cooldown_seconds)
    recent = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.character_id == character.id,
            ChatMessage.posted_at >= since,
        )
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    if recent.scalar_one_or_none():
        raise HTTPException(
            status_code=429,
            detail=f"Wait {settings.chat_cooldown_seconds}s between messages",
        )

    now = utcnow()
    msg = ChatMessage(
        state_id=state_id,
        character_id=character.id,
        display_name=character.display_name,
        body=text,
        posted_at=now,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    payload = {
        "id": msg.id,
        "state_id": msg.state_id,
        "character_id": msg.character_id,
        "display_name": msg.display_name,
        "body": msg.body,
        "posted_at": msg.posted_at,
    }
    try:
        from app.realtime import emit_chat

        await emit_chat(payload)
    except Exception:
        pass
    return payload
