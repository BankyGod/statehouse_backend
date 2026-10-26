from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.character import Character
from app.models.job import Job, JobListing
from app.models.permit import Permit, PermitStatus, PermitType
from app.services.character_service import ensure_can_act, ensure_energy
from app.services.education_service import get_highest_education_level


async def list_jobs_in_state(db: AsyncSession, state_id: int) -> list[JobListing]:
    result = await db.execute(
        select(JobListing).where(
            JobListing.state_id == state_id,
            JobListing.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def _has_work_permit(
    db: AsyncSession, character: Character, state_id: int
) -> bool:
    if character.home_state_id == state_id:
        return True
    result = await db.execute(
        select(Permit).where(
            Permit.character_id == character.id,
            Permit.state_id == state_id,
            Permit.permit_type == PermitType.WORK,
            Permit.status == PermitStatus.ACTIVE,
            Permit.expires_at > utcnow(),
        )
    )
    return result.scalar_one_or_none() is not None


async def hire(
    db: AsyncSession, character: Character, listing_id: int
) -> Job:
    ensure_can_act(character)
    listing = await db.get(JobListing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Job listing not found")

    if not await _has_work_permit(db, character, listing.state_id):
        raise HTTPException(
            status_code=403,
            detail="Work permit required for this state",
        )

    edu_level = await get_highest_education_level(db, character.id)
    if edu_level < listing.min_education_level:
        raise HTTPException(status_code=400, detail="Education level too low")

    if listing.requires_clean_record and character.heat > 10:
        raise HTTPException(
            status_code=400,
            detail="Background check failed (heat too high / record)",
        )
    if listing.requires_clean_record and character.criminal_record_summary:
        raise HTTPException(status_code=400, detail="Clean criminal record required")

    existing = await db.execute(
        select(Job).where(Job.character_id == character.id, Job.is_active.is_(True))
    )
    current = existing.scalar_one_or_none()
    if current:
        current.is_active = False

    job = Job(
        character_id=character.id,
        listing_id=listing.id,
        state_id=listing.state_id,
        hired_at=utcnow(),
        shifts_completed=0,
        is_active=True,
    )
    db.add(job)
    character.current_state_id = listing.state_id
    await db.flush()
    await db.refresh(job)
    return job


async def work_shift(db: AsyncSession, character: Character) -> dict:
    ensure_can_act(character)
    result = await db.execute(
        select(Job).where(Job.character_id == character.id, Job.is_active.is_(True))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=400, detail="Not employed")

    listing = await db.get(JobListing, job.listing_id)
    if listing is None:
        raise HTTPException(status_code=400, detail="Job listing missing")

    ensure_energy(character, listing.energy_cost)

    # Block if another activity is in progress that isn't a short job (education etc.)
    busy = await db.execute(
        select(Activity).where(
            Activity.character_id == character.id,
            Activity.status == ActivityStatus.IN_PROGRESS,
            Activity.activity_type == ActivityType.EDUCATION,
            Activity.completes_at > utcnow(),
        )
    )
    # Part-time study allowed — education does not block shifts

    now = utcnow()
    completes = now + timedelta(minutes=listing.shift_minutes)
    character.energy -= listing.energy_cost
    character.last_energy_at = now

    wage = float(listing.wage_per_shift)
    from app.services import social_service

    for event in await social_service.list_active_events(db):
        if event["effect_key"] == "job_pay_boost":
            wage = round(wage * float(event["effect_value"]), 2)

    from app.services import treasury_service

    pay = await treasury_service.pay_taxable_income(
        db,
        character,
        wage,
        note=f"Income tax — shift {listing.title}",
    )
    job.shifts_completed += 1

    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.JOB_SHIFT,
        status=ActivityStatus.COMPLETED,
        title=f"Shift: {listing.title}",
        age_gain_years=0,
        energy_cost=listing.energy_cost,
        cash_delta=pay["net"],
        started_at=now,
        completes_at=completes,
        completed_at=now,
        ref_type="job",
        ref_id=job.id,
    )
    db.add(activity)
    await db.flush()
    from app.services.notify_service import broadcast_activity, broadcast_character

    await broadcast_activity(activity)
    await broadcast_character(character)

    return {
        "wage": wage,
        "gross": pay["gross"],
        "tax": pay["tax"],
        "tax_rate": pay["rate"],
        "net": pay["net"],
        "energy_spent": listing.energy_cost,
        "shifts_completed": job.shifts_completed,
        "cash": character.cash,
        "energy": character.energy,
    }
