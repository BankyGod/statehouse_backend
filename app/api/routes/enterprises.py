from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import enterprise_service

router = APIRouter(prefix="/enterprises", tags=["enterprises"])


@router.get("")
async def list_enterprises(db: AsyncSession = Depends(get_db)):
    return {"enterprises": await enterprise_service.list_enterprises(db)}
