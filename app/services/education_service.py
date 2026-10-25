from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.character import Character
from app.models.education import (
    EDUCATION_CATALOG,
    EducationEnrollment,
    EducationTrack,
    EnrollmentStatus,
)
from app.services.character_service import ensure_can_act


async def list_catalog() -> list[dict]:
    return [
        {"track": track, **meta} for track, meta in EDUCATION_CATALOG.items()
    ]


async def get_highest_education_level(db: AsyncSession, character_id: int) -> int:
    result = await db.execute(
        select(EducationEnrollment).where(
            EducationEnrollment.character_id == character_id,
            EducationEnrollment.status == EnrollmentStatus.COMPLETED,
        )
    )
    enrollments = result.scalars().all()
    if not enrollments:
        return 0
    return max(e.education_level for e in enrollments)


async def enroll(
    db: AsyncSession, character: Character, track: EducationTrack
) -> EducationEnrollment:
    ensure_can_act(character)
    meta = EDUCATION_CATALOG[track]

    active = await db.execute(
        select(EducationEnrollment).where(
            EducationEnrollment.character_id == character.id,
            EducationEnrollment.status == EnrollmentStatus.ENROLLED,
        )
    )
    if active.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already enrolled in a course")

    if character.cash < meta["cost"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    now = utcnow()
    completes = now + timedelta(days=meta["real_days"])
    character.cash -= meta["cost"]

    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.EDUCATION,
        status=ActivityStatus.IN_PROGRESS,
        title=meta["label"],
        description=f"Studying {meta['label']}",
        age_gain_years=meta["age_years"],
        energy_cost=0,
        cash_delta=-meta["cost"],
        started_at=now,
        completes_at=completes,
    )
    db.add(activity)
    await db.flush()
    from app.services.notify_service import broadcast_activity, broadcast_character

    await broadcast_activity(activity)
    await broadcast_character(character)

    enrollment = EducationEnrollment(
        character_id=character.id,
        track=track,
        status=EnrollmentStatus.ENROLLED,
        title=meta["label"],
        cost_paid=meta["cost"],
        age_gain_years=meta["age_years"],
        education_level=meta["level"],
        started_at=now,
        completes_at=completes,
        activity_id=activity.id,
    )
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def complete_due_education(db: AsyncSession, character: Character) -> list[EducationEnrollment]:
    now = utcnow()
    result = await db.execute(
        select(EducationEnrollment).where(
            EducationEnrollment.character_id == character.id,
            EducationEnrollment.status == EnrollmentStatus.ENROLLED,
            EducationEnrollment.completes_at <= now,
        )
    )
    done: list[EducationEnrollment] = []
    for enrollment in result.scalars().all():
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = now
        character.age_years += enrollment.age_gain_years
        if enrollment.activity_id:
            activity = await db.get(Activity, enrollment.activity_id)
            if activity:
                activity.status = ActivityStatus.COMPLETED
                activity.completed_at = now
                from app.services.notify_service import broadcast_activity

                await broadcast_activity(activity)
        done.append(enrollment)
    if done:
        from app.services import notify_service

        await notify_service.push(
            db,
            character.id,
            "Education complete",
            body=", ".join(e.title for e in done),
            category="education",
        )
        await db.flush()
        from app.services.notify_service import broadcast_character

        await broadcast_character(character)
    return done
