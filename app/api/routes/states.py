from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.state import State
from app.schemas.state import StateOut, StateSummaryOut

router = APIRouter(prefix="/states", tags=["states"])


@router.get("", response_model=list[StateSummaryOut])
async def list_states(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(State).order_by(State.name))
    return list(result.scalars().all())


@router.get("/{state_id}", response_model=StateOut)
async def get_state(state_id: int, db: AsyncSession = Depends(get_db)):
    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")
    return state


@router.get("/slug/{slug}", response_model=StateOut)
async def get_state_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(State).where(State.slug == slug))
    state = result.scalar_one_or_none()
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")
    return state
