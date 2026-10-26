from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.education import EducationEnrollment
from app.models.user import User
from app.schemas.life import EducationCatalogItem, EnrollRequest, EnrollmentOut
from app.services import character_service, education_service

router = APIRouter(prefix="/education", tags=["education"])


@router.get("/catalog", response_model=list[EducationCatalogItem])
async def catalog():
    return await education_service.list_catalog()


@router.get("/institutions")
async def institutions(
    state_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return {
        "institutions": await education_service.list_institutions(
            db, state_id=state_id, kind=kind
        )
    }


@router.get("/institutions/{institution_id}/programs")
async def institution_programs(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
):
    return {
        "programs": await education_service.list_programs(db, institution_id)
    }


@router.get("/programs")
async def all_programs(db: AsyncSession = Depends(get_db)):
    return {"programs": await education_service.list_all_programs(db)}


@router.post("/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(
    payload: EnrollRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    await education_service.complete_due_education(db, character)
    if payload.program_id is not None:
        enrollment = await education_service.enroll_in_program(
            db, character, payload.program_id
        )
    elif payload.track is not None:
        enrollment = await education_service.enroll(db, character, payload.track)
    else:
        raise HTTPException(
            status_code=422, detail="Provide program_id (preferred) or track"
        )
    outs = await education_service.enrollments_to_out(db, [enrollment])
    return outs[0]


@router.get("/me", response_model=list[EnrollmentOut])
async def my_enrollments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    await education_service.complete_due_education(db, character)
    result = await db.execute(
        select(EducationEnrollment).where(
            EducationEnrollment.character_id == character.id
        )
    )
    return await education_service.enrollments_to_out(
        db, list(result.scalars().all())
    )
