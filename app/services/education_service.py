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
    EducationInstitution,
    EducationProgram,
    EducationTrack,
    EnrollmentStatus,
)
from app.models.enterprise import StateEnterprise
from app.models.state import State
from app.schemas.life import EnrollmentOut
from app.services.character_service import ensure_can_act


def _enum_str(value: object | None) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def enrollment_to_out(
    enrollment: EducationEnrollment,
    institution: EducationInstitution | None = None,
) -> EnrollmentOut:
    status = _enum_str(enrollment.status) or str(enrollment.status)
    track = enrollment.track
    return EnrollmentOut(
        id=enrollment.id,
        track=track.value if hasattr(track, "value") else track,
        status=status,
        title=enrollment.title,
        cost_paid=enrollment.cost_paid,
        age_gain_years=enrollment.age_gain_years,
        education_level=enrollment.education_level,
        institution_id=enrollment.institution_id,
        program_id=enrollment.program_id,
        institution_name=institution.name if institution else None,
        institution_slug=institution.slug if institution else None,
        institution_kind=_enum_str(institution.kind) if institution else None,
        institution_ownership=_enum_str(institution.ownership) if institution else None,
        started_at=enrollment.started_at,
        completes_at=enrollment.completes_at,
        completed_at=enrollment.completed_at,
    )


async def enrollments_to_out(
    db: AsyncSession, enrollments: list[EducationEnrollment]
) -> list[EnrollmentOut]:
    inst_ids = {e.institution_id for e in enrollments if e.institution_id}
    institutions: dict[int, EducationInstitution] = {}
    if inst_ids:
        result = await db.execute(
            select(EducationInstitution).where(EducationInstitution.id.in_(inst_ids))
        )
        institutions = {i.id: i for i in result.scalars().all()}
    return [
        enrollment_to_out(
            e, institutions.get(e.institution_id) if e.institution_id else None
        )
        for e in enrollments
    ]


async def ensure_education_seeded(db: AsyncSession) -> int:
    # Lazy import avoids circular import via app.seed.__init__
    from app.seed.education_data import INSTITUTIONS, program_metrics

    result = await db.execute(select(EducationInstitution.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0

    states = {s.slug: s for s in (await db.execute(select(State))).scalars().all()}
    enterprises = {
        e.slug: e
        for e in (await db.execute(select(StateEnterprise))).scalars().all()
    }

    created_programs = 0
    for raw in INSTITUTIONS:
        state = states.get(raw["state_slug"])
        if state is None:
            continue
        ent = None
        if raw.get("enterprise_slug"):
            ent = enterprises.get(raw["enterprise_slug"])
        inst = EducationInstitution(
            slug=raw["slug"],
            name=raw["name"],
            kind=raw["kind"],
            ownership=raw["ownership"],
            state_id=state.id,
            enterprise_id=ent.id if ent else None,
            prestige=raw["prestige"],
            description=raw.get("description"),
            is_open=True,
        )
        db.add(inst)
        await db.flush()

        for prog in raw["programs"]:
            title = prog[0]
            track = prog[1]
            min_level = prog[2]
            cost_mult = prog[3] if len(prog) > 3 else 1.0
            metrics = program_metrics(track, cost_mult)
            db.add(
                EducationProgram(
                    institution_id=inst.id,
                    track=track,
                    title=title,
                    real_days=metrics["real_days"],
                    age_years=metrics["age_years"],
                    cost=metrics["cost"],
                    level=metrics["level"],
                    min_education_level=min_level,
                    is_active=True,
                )
            )
            created_programs += 1
    await db.flush()
    return created_programs


async def list_catalog() -> list[dict]:
    """Legacy flat track catalog (kept for older clients)."""
    return [{"track": track, **meta} for track, meta in EDUCATION_CATALOG.items()]


async def list_institutions(
    db: AsyncSession,
    *,
    state_id: int | None = None,
    kind: str | None = None,
) -> list[dict]:
    await ensure_education_seeded(db)
    stmt = select(EducationInstitution).where(EducationInstitution.is_open.is_(True))
    if state_id is not None:
        stmt = stmt.where(EducationInstitution.state_id == state_id)
    if kind:
        stmt = stmt.where(EducationInstitution.kind == kind)
    stmt = stmt.order_by(EducationInstitution.prestige.desc(), EducationInstitution.name)
    result = await db.execute(stmt)
    out = []
    for inst in result.scalars().all():
        state = await db.get(State, inst.state_id)
        out.append(
            {
                "id": inst.id,
                "slug": inst.slug,
                "name": inst.name,
                "kind": inst.kind.value,
                "ownership": inst.ownership.value,
                "state_id": inst.state_id,
                "state_name": state.name if state else None,
                "state_slug": state.slug if state else None,
                "enterprise_id": inst.enterprise_id,
                "prestige": inst.prestige,
                "description": inst.description,
                "is_open": inst.is_open,
            }
        )
    return out


async def list_programs(db: AsyncSession, institution_id: int) -> list[dict]:
    await ensure_education_seeded(db)
    inst = await db.get(EducationInstitution, institution_id)
    if inst is None or not inst.is_open:
        raise HTTPException(status_code=404, detail="Institution not found")
    result = await db.execute(
        select(EducationProgram)
        .where(
            EducationProgram.institution_id == institution_id,
            EducationProgram.is_active.is_(True),
        )
        .order_by(EducationProgram.level, EducationProgram.title)
    )
    return [
        {
            "id": p.id,
            "institution_id": p.institution_id,
            "track": p.track.value,
            "title": p.title,
            "real_days": p.real_days,
            "age_years": p.age_years,
            "cost": p.cost,
            "level": p.level,
            "min_education_level": p.min_education_level,
            "capacity": p.capacity,
        }
        for p in result.scalars().all()
    ]


async def list_all_programs(db: AsyncSession) -> list[dict]:
    """Flattened catalog of concrete programs for browsing."""
    await ensure_education_seeded(db)
    result = await db.execute(
        select(EducationProgram, EducationInstitution)
        .join(
            EducationInstitution,
            EducationProgram.institution_id == EducationInstitution.id,
        )
        .where(
            EducationProgram.is_active.is_(True),
            EducationInstitution.is_open.is_(True),
        )
        .order_by(EducationInstitution.name, EducationProgram.title)
    )
    out = []
    for prog, inst in result.all():
        out.append(
            {
                "id": prog.id,
                "institution_id": inst.id,
                "institution_name": inst.name,
                "institution_ownership": inst.ownership.value,
                "state_id": inst.state_id,
                "track": prog.track.value,
                "title": prog.title,
                "real_days": prog.real_days,
                "age_years": prog.age_years,
                "cost": prog.cost,
                "level": prog.level,
                "min_education_level": prog.min_education_level,
            }
        )
    return out


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


async def enroll_in_program(
    db: AsyncSession, character: Character, program_id: int
) -> EducationEnrollment:
    ensure_can_act(character)
    await ensure_education_seeded(db)
    program = await db.get(EducationProgram, program_id)
    if program is None or not program.is_active:
        raise HTTPException(status_code=404, detail="Program not found")
    institution = await db.get(EducationInstitution, program.institution_id)
    if institution is None or not institution.is_open:
        raise HTTPException(status_code=400, detail="Institution is closed")

    active = await db.execute(
        select(EducationEnrollment).where(
            EducationEnrollment.character_id == character.id,
            EducationEnrollment.status == EnrollmentStatus.ENROLLED,
        )
    )
    if active.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already enrolled in a course")

    highest = await get_highest_education_level(db, character.id)
    if highest < program.min_education_level:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requires education level {program.min_education_level} "
                f"(you have {highest})"
            ),
        )

    if character.cash < program.cost:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    now = utcnow()
    completes = now + timedelta(days=program.real_days)
    character.cash -= program.cost

    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.EDUCATION,
        status=ActivityStatus.IN_PROGRESS,
        title=program.title,
        description=f"Studying {program.title} at {institution.name}",
        age_gain_years=program.age_years,
        energy_cost=0,
        cash_delta=-program.cost,
        started_at=now,
        completes_at=completes,
        ref_type="education_program",
        ref_id=program.id,
    )
    db.add(activity)
    await db.flush()
    from app.services.notify_service import broadcast_activity, broadcast_character

    await broadcast_activity(activity)
    await broadcast_character(character)

    enrollment = EducationEnrollment(
        character_id=character.id,
        track=program.track,
        institution_id=institution.id,
        program_id=program.id,
        status=EnrollmentStatus.ENROLLED,
        title=f"{program.title} — {institution.name}",
        cost_paid=program.cost,
        age_gain_years=program.age_years,
        education_level=program.level,
        started_at=now,
        completes_at=completes,
        activity_id=activity.id,
    )
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def enroll(
    db: AsyncSession, character: Character, track: EducationTrack
) -> EducationEnrollment:
    """Legacy enroll-by-track: pick cheapest open program for that track."""
    await ensure_education_seeded(db)
    result = await db.execute(
        select(EducationProgram)
        .join(EducationInstitution)
        .where(
            EducationProgram.track == track,
            EducationProgram.is_active.is_(True),
            EducationInstitution.is_open.is_(True),
        )
        .order_by(EducationProgram.cost.asc())
        .limit(1)
    )
    program = result.scalar_one_or_none()
    if program is None:
        # Fallback to catalog-only enrollment (pre-seed environments)
        return await _enroll_catalog_only(db, character, track)
    return await enroll_in_program(db, character, program.id)


async def _enroll_catalog_only(
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


async def complete_due_education(
    db: AsyncSession, character: Character
) -> list[EducationEnrollment]:
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
