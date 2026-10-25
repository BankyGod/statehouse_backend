"""Socket.IO realtime layer — activities, notifications, chat, HUD patches."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import socketio
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_access_token

settings = get_settings()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origin_list or "*",
    logger=False,
    engineio_logger=False,
    ping_interval=25,
    ping_timeout=60,
)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def notification_payload(note) -> dict:
    return {
        "id": note.id,
        "character_id": note.character_id,
        "category": note.category,
        "title": note.title,
        "body": note.body,
        "is_read": note.is_read,
        "ref_type": note.ref_type,
        "ref_id": note.ref_id,
        "posted_at": _iso(note.posted_at),
    }


def activity_payload(activity) -> dict:
    return {
        "id": activity.id,
        "character_id": activity.character_id,
        "activity_type": (
            activity.activity_type.value
            if hasattr(activity.activity_type, "value")
            else str(activity.activity_type)
        ),
        "status": (
            activity.status.value
            if hasattr(activity.status, "value")
            else str(activity.status)
        ),
        "title": activity.title,
        "description": activity.description,
        "age_gain_years": activity.age_gain_years,
        "energy_cost": activity.energy_cost,
        "cash_delta": activity.cash_delta,
        "started_at": _iso(activity.started_at),
        "completes_at": _iso(activity.completes_at),
        "completed_at": _iso(activity.completed_at),
        "ref_type": activity.ref_type,
        "ref_id": activity.ref_id,
    }


def character_payload(character) -> dict:
    return {
        "id": character.id,
        "display_name": character.display_name,
        "home_state_id": character.home_state_id,
        "current_state_id": character.current_state_id,
        "cash": character.cash,
        "bank_balance": character.bank_balance,
        "energy": character.energy,
        "max_energy": character.max_energy,
        "nerve": getattr(character, "nerve", 20),
        "max_nerve": getattr(character, "max_nerve", 20),
        "heat": character.heat,
        "age_years": character.age_years,
        "reputation": character.reputation,
        "health": character.health,
        "max_health": character.max_health,
        "is_jailed": character.is_jailed,
        "jail_until": _iso(character.jail_until),
        "is_hospitalized": character.is_hospitalized,
        "hospital_until": _iso(character.hospital_until),
        "is_traveling": character.is_traveling,
        "travel_until": _iso(character.travel_until),
        "travel_destination_id": character.travel_destination_id,
        "is_homeless": character.is_homeless,
        "active_residence_id": character.active_residence_id,
        "strength": getattr(character, "strength", 10.0),
        "defense": getattr(character, "defense", 10.0),
        "speed": getattr(character, "speed", 10.0),
        "dexterity": getattr(character, "dexterity", 10.0),
        "faction_id": getattr(character, "faction_id", None),
    }


async def emit_to_character(character_id: int, event: str, data: dict) -> None:
    await sio.emit(event, data, room=f"character:{character_id}")


async def emit_notification(note) -> None:
    await emit_to_character(
        note.character_id, "notification", notification_payload(note)
    )


async def emit_activity(activity) -> None:
    await emit_to_character(
        activity.character_id, "activity", activity_payload(activity)
    )


async def emit_character(character) -> None:
    await emit_to_character(
        character.id, "character", character_payload(character)
    )


async def emit_chat(message: dict) -> None:
    state_id = message.get("state_id")
    if state_id is None:
        return
    payload = {k: _iso(v) for k, v in message.items()}
    await sio.emit("chat:message", payload, room=f"state:{state_id}")


@sio.event
async def connect(sid, environ, auth):
    """Authenticate with JWT: `io(url, { auth: { token } })`."""
    token = None
    if isinstance(auth, dict):
        token = auth.get("token") or auth.get("access_token")
    if not token:
        # Also accept query ?token=
        qs = environ.get("QUERY_STRING") or ""
        for part in qs.split("&"):
            if part.startswith("token="):
                token = part.split("=", 1)[1]
                break
    if not token:
        return False

    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        return False

    user_id = int(payload["sub"])
    from app.core.database import get_session_factory
    from app.models.character import Character
    from app.models.user import User

    factory = get_session_factory()
    async with factory() as db:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            return False
        result = await db.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if character is None:
            # Allow connect before character create — limited rooms
            await sio.save_session(
                sid, {"user_id": user.id, "character_id": None}
            )
            await sio.enter_room(sid, f"user:{user.id}")
            return True

        await sio.save_session(
            sid,
            {
                "user_id": user.id,
                "character_id": character.id,
                "home_state_id": character.home_state_id,
                "current_state_id": character.current_state_id,
            },
        )
        await sio.enter_room(sid, f"user:{user.id}")
        await sio.enter_room(sid, f"character:{character.id}")
        await sio.enter_room(sid, f"state:{character.home_state_id}")
        if character.current_state_id != character.home_state_id:
            await sio.enter_room(sid, f"state:{character.current_state_id}")

        await sio.emit(
            "connected",
            {
                "user_id": user.id,
                "character_id": character.id,
                "display_name": character.display_name,
            },
            to=sid,
        )
        await sio.emit("character", character_payload(character), to=sid)
    return True


@sio.event
async def disconnect(sid):
    return


@sio.event
async def join_state(sid, data):
    """Subscribe to a state chat channel (must be home or current)."""
    session = await sio.get_session(sid)
    character_id = session.get("character_id")
    if not character_id:
        return {"ok": False, "error": "No character"}
    try:
        state_id = int((data or {}).get("state_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid state_id"}

    from app.core.database import get_session_factory
    from app.models.character import Character

    factory = get_session_factory()
    async with factory() as db:
        character = await db.get(Character, character_id)
        if character is None:
            return {"ok": False, "error": "Character missing"}
        if state_id not in (character.home_state_id, character.current_state_id):
            return {"ok": False, "error": "Not allowed in that state chat"}
        await sio.enter_room(sid, f"state:{state_id}")
        return {"ok": True, "state_id": state_id}


@sio.event
async def leave_state(sid, data):
    try:
        state_id = int((data or {}).get("state_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    session = await sio.get_session(sid)
    # Don't leave home/current auto-joined rooms from a bad leave
    if state_id in (
        session.get("home_state_id"),
        session.get("current_state_id"),
    ):
        return {"ok": True, "kept": True}
    await sio.leave_room(sid, f"state:{state_id}")
    return {"ok": True}


@sio.event
async def ping_hud(sid):
    """Client can request a fresh character snapshot (e.g. after long idle)."""
    session = await sio.get_session(sid)
    character_id = session.get("character_id")
    if not character_id:
        return {"ok": False}
    from app.core.database import get_session_factory
    from app.models.character import Character
    from app.services.tick_service import tick_character

    factory = get_session_factory()
    async with factory() as db:
        character = await db.get(Character, character_id)
        if character is None:
            return {"ok": False}
        await tick_character(db, character)
        await db.commit()
        await sio.emit("character", character_payload(character), to=sid)
    return {"ok": True}
