from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.item import Notification


async def push(
    db: AsyncSession,
    character_id: int,
    title: str,
    *,
    body: str | None = None,
    category: str = "general",
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> Notification:
    note = Notification(
        character_id=character_id,
        category=category,
        title=title,
        body=body,
        is_read=False,
        ref_type=ref_type,
        ref_id=ref_id,
        posted_at=utcnow(),
    )
    db.add(note)
    await db.flush()
    try:
        from app.realtime import emit_notification

        await emit_notification(note)
    except Exception:
        pass
    return note


async def list_notifications(
    db: AsyncSession, character_id: int, *, limit: int = 40, unread_only: bool = False
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.character_id == character_id)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_read(
    db: AsyncSession, character_id: int, notification_id: int | None = None
) -> int:
    if notification_id is not None:
        note = await db.get(Notification, notification_id)
        if note and note.character_id == character_id and not note.is_read:
            note.is_read = True
            await db.flush()
            return 1
        return 0
    result = await db.execute(
        select(Notification).where(
            Notification.character_id == character_id,
            Notification.is_read.is_(False),
        )
    )
    count = 0
    for note in result.scalars().all():
        note.is_read = True
        count += 1
    await db.flush()
    return count


async def list_activities(
    db: AsyncSession, character_id: int, *, limit: int = 40
) -> list[Activity]:
    result = await db.execute(
        select(Activity)
        .where(Activity.character_id == character_id)
        .order_by(Activity.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def broadcast_activity(activity: Activity) -> None:
    try:
        from app.realtime import emit_activity

        await emit_activity(activity)
    except Exception:
        pass


async def broadcast_character(character) -> None:
    try:
        from app.realtime import emit_character

        await emit_character(character)
    except Exception:
        pass


async def log_instant_activity(
    db: AsyncSession,
    character_id: int,
    activity_type: ActivityType,
    title: str,
    *,
    description: str | None = None,
    cash_delta: float = 0.0,
    energy_cost: int = 0,
) -> Activity:
    now = utcnow()
    activity = Activity(
        character_id=character_id,
        activity_type=activity_type,
        status=ActivityStatus.COMPLETED,
        title=title,
        description=description,
        age_gain_years=0,
        energy_cost=energy_cost,
        cash_delta=cash_delta,
        started_at=now,
        completes_at=now,
        completed_at=now,
    )
    db.add(activity)
    await db.flush()
    await broadcast_activity(activity)
    return activity
