from fastapi import APIRouter, Depends
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


@router.post("/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(
    payload: EnrollRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    await education_service.complete_due_education(db, character)
    return await education_service.enroll(db, character, payload.track)


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
    return list(result.scalars().all())
