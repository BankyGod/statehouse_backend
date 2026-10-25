from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import TravelQuoteOut, TravelQuoteRequest, TravelStartRequest
from app.services import character_service, travel_service
from app.services.travel_service import quote_travel

router = APIRouter(prefix="/travel", tags=["travel"])


@router.post("/quote", response_model=TravelQuoteOut)
async def quote(
    payload: TravelQuoteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    base = quote_travel(character.current_state_id, payload.to_state_id)
    return TravelQuoteOut(
        from_state_id=character.current_state_id,
        to_state_id=payload.to_state_id,
        cost=base["cost"],
        minutes=base["minutes"],
        discounted_cost=round(base["cost"] * 0.75, 2),
    )


@router.post("/start")
async def start(
    payload: TravelStartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await travel_service.start_travel(db, character, payload.to_state_id)
