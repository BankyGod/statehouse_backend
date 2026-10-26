from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import TravelQuoteOut, TravelQuoteRequest, TravelStartRequest
from app.services import character_service, travel_service
from app.services.travel_service import quote_travel

router = APIRouter(prefix="/travel", tags=["travel"])


@router.get("/options")
async def options(
    to_state_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {
        "options": await travel_service.list_travel_options(
            db, character, to_state_id
        )
    }


@router.post("/quote", response_model=TravelQuoteOut)
async def quote(
    payload: TravelQuoteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    if payload.carrier_id is not None:
        data = await travel_service.quote_carrier(
            db, character, payload.to_state_id, payload.carrier_id
        )
        return TravelQuoteOut(**data)
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
    return await travel_service.start_travel(
        db, character, payload.to_state_id, carrier_id=payload.carrier_id
    )
