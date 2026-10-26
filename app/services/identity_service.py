"""Unique public names (username + display_name) and player search."""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.user import User

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-. ]{3,64}$")


def normalize_public_name(raw: str) -> str:
    name = " ".join((raw or "").strip().split())
    if len(name) < 3 or len(name) > 64:
        raise HTTPException(
            status_code=400, detail="Name must be 3–64 characters"
        )
    if not _NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Use letters, numbers, spaces, _ - . only",
        )
    return name


async def is_public_name_taken(
    db: AsyncSession, name: str, *, exclude_character_id: int | None = None
) -> bool:
    """True if username or display_name already uses this name (case-insensitive)."""
    key = name.strip().lower()
    if not key:
        return False

    user_q = await db.execute(
        select(User.id).where(func.lower(User.username) == key).limit(1)
    )
    if user_q.scalar_one_or_none() is not None:
        return True

    stmt = select(Character.id).where(func.lower(Character.display_name) == key)
    if exclude_character_id is not None:
        stmt = stmt.where(Character.id != exclude_character_id)
    char_q = await db.execute(stmt.limit(1))
    return char_q.scalar_one_or_none() is not None


async def assert_public_name_available(
    db: AsyncSession, name: str, *, exclude_character_id: int | None = None
) -> str:
    cleaned = normalize_public_name(name)
    if await is_public_name_taken(
        db, cleaned, exclude_character_id=exclude_character_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{cleaned}" is already registered as a username or display name. '
                "Choose a different name."
            ),
        )
    return cleaned


async def check_name_availability(db: AsyncSession, name: str) -> dict:
    try:
        cleaned = normalize_public_name(name)
    except HTTPException as exc:
        return {
            "name": name,
            "available": False,
            "normalized": None,
            "reason": exc.detail,
        }
    taken = await is_public_name_taken(db, cleaned)
    return {
        "name": name,
        "normalized": cleaned,
        "available": not taken,
        "reason": None if not taken else "Already registered as a username or display name",
    }


async def search_players(
    db: AsyncSession,
    query: str,
    *,
    exclude_character_id: int | None = None,
    limit: int = 12,
) -> list[dict]:
    """Search by character id, display name, or account username."""
    q = (query or "").strip()
    if len(q) < 1:
        return []

    limit = max(1, min(int(limit), 25))
    rows: list[Character] = []

    # Exact / numeric id lookup
    if q.isdigit():
        cid = int(q)
        character = await db.get(Character, cid)
        if character and not getattr(character, "is_npc", False):
            if exclude_character_id is None or character.id != exclude_character_id:
                rows.append(character)

    # Username → linked character
    user_result = await db.execute(
        select(User).where(func.lower(User.username) == q.lower()).limit(1)
    )
    user = user_result.scalar_one_or_none()
    if user is not None:
        char_result = await db.execute(
            select(Character).where(Character.user_id == user.id).limit(1)
        )
        linked = char_result.scalar_one_or_none()
        if linked and not getattr(linked, "is_npc", False):
            if exclude_character_id is None or linked.id != exclude_character_id:
                if all(r.id != linked.id for r in rows):
                    rows.append(linked)

    # Fuzzy display name (and similar)
    pattern = f"%{q.lower()}%"
    stmt = (
        select(Character)
        .where(
            Character.is_npc.is_(False),
            func.lower(Character.display_name).like(pattern),
        )
        .order_by(Character.display_name.asc())
        .limit(limit)
    )
    if exclude_character_id is not None:
        stmt = stmt.where(Character.id != exclude_character_id)
    name_hits = list((await db.execute(stmt)).scalars().all())
    for hit in name_hits:
        if all(r.id != hit.id for r in rows):
            rows.append(hit)

    # Also match username substring → character
    if len(q) >= 2:
        user_hits = await db.execute(
            select(User)
            .where(func.lower(User.username).like(pattern), User.is_bot.is_(False))
            .order_by(User.username.asc())
            .limit(limit)
        )
        for u in user_hits.scalars().all():
            char_result = await db.execute(
                select(Character).where(Character.user_id == u.id).limit(1)
            )
            linked = char_result.scalar_one_or_none()
            if (
                linked
                and not getattr(linked, "is_npc", False)
                and (exclude_character_id is None or linked.id != exclude_character_id)
                and all(r.id != linked.id for r in rows)
            ):
                rows.append(linked)

    out: list[dict] = []
    for c in rows[:limit]:
        uname = None
        if c.user_id:
            u = await db.get(User, c.user_id)
            uname = u.username if u else None
        out.append(
            {
                "id": c.id,
                "display_name": c.display_name,
                "username": uname,
                "label": f"{c.display_name} (#{c.id})",
            }
        )
    return out
