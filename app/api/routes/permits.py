from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import PermitApplyRequest, PermitOut
from app.services import character_service, permit_service

router = APIRouter(prefix="/permits", tags=["permits"])


@router.post("/apply", response_model=PermitOut, status_code=201)
async def apply(
    payload: PermitApplyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await permit_service.apply_permit(
        db, character, payload.state_id, payload.permit_type
    )


@router.get("/me", response_model=list[PermitOut])
async def my_permits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await permit_service.list_permits(db, character.id)
