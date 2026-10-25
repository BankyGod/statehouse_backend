from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import ClinicHealRequest, HealthStatusOut
from app.services import character_service, health_service

router = APIRouter(prefix="/medical", tags=["medical"])


@router.get("/me", response_model=HealthStatusOut)
async def my_health(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    settings = get_settings()
    from app.services import jail_service

    status = jail_service.hospital_status(character)
    return HealthStatusOut(
        health=character.health,
        max_health=character.max_health,
        is_hospitalized=character.is_hospitalized,
        hospital_until=character.hospital_until,
        condition=character.condition,
        clinic_cost_per_hp=settings.clinic_heal_cost_per_hp,
        hospital_base_hours=settings.hospital_base_hours,
        seconds_remaining=status["seconds_remaining"],
    )


@router.post("/clinic")
async def clinic(
    payload: ClinicHealRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await health_service.clinic_heal(db, character, payload.hp_amount)


@router.post("/hospital")
async def hospital(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await health_service.hospitalize(db, character)
