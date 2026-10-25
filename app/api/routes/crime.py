from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import CrimeCatalogItem, CrimeCommitRequest, CrimeResultOut
from app.services import character_service, crime_service

router = APIRouter(prefix="/crime", tags=["crime"])


@router.get("/catalog", response_model=list[CrimeCatalogItem])
async def catalog():
    return crime_service.list_catalog()


@router.post("/commit", response_model=CrimeResultOut)
async def commit(
    payload: CrimeCommitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await crime_service.commit_crime(db, character, payload.crime_type)


@router.get("/history")
async def crime_history(
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await crime_service.history(db, character.id, limit=limit)
