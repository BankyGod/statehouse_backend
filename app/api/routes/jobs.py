from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.job import Job
from app.models.user import User
from app.schemas.life import HireRequest, JobListingOut, JobOut
from app.services import character_service, job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/listings", response_model=list[JobListingOut])
async def listings(
    state_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    target = state_id or character.current_state_id
    return await job_service.list_jobs_in_state(db, target)


@router.post("/hire", response_model=JobOut, status_code=201)
async def hire(
    payload: HireRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await job_service.hire(db, character, payload.listing_id)


@router.get("/me", response_model=JobOut | None)
async def my_job(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    from app.services import office_pay_service

    # Political office ends employee roles; company payroll ends leftover state jobs
    if await office_pay_service.holds_political_office(db, character):
        await office_pay_service.end_employee_jobs_for_office(
            db, character, reason="Holds political office"
        )
    else:
        await job_service.clear_state_job_if_company_employed(db, character)
    result = await db.execute(
        select(Job).where(Job.character_id == character.id, Job.is_active.is_(True))
    )
    return result.scalar_one_or_none()


@router.post("/work")
async def work(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await job_service.work_shift(db, character)
