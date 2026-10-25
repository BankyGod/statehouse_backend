from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.character import Character
from app.models.permit import Permit, PermitStatus, PermitType
from app.models.state import State
from app.models.travel import TravelLog
from app.services.character_service import ensure_not_jailed


def quote_travel(from_state_id: int, to_state_id: int) -> dict:
    settings = get_settings()
    # Cheap distance proxy: farther IDs cost a bit more
    hop = abs(to_state_id - from_state_id)
    cost = settings.travel_base_cost + hop * 3.0
    minutes = settings.travel_base_minutes + hop * 2
    return {"cost": round(cost, 2), "minutes": minutes}


async def _has_travel_permit(
    db: AsyncSession, character: Character, state_id: int
) -> bool:
    if character.home_state_id == state_id:
        return True
    result = await db.execute(
        select(Permit).where(
            Permit.character_id == character.id,
            Permit.state_id == state_id,
            Permit.permit_type == PermitType.TRAVEL,
            Permit.status == PermitStatus.ACTIVE,
            Permit.expires_at > utcnow(),
        )
    )
    return result.scalar_one_or_none() is not None


async def start_travel(
    db: AsyncSession, character: Character, to_state_id: int
) -> dict:
    ensure_not_jailed(character)
    if character.is_traveling:
        raise HTTPException(status_code=400, detail="Already traveling")
    if to_state_id == character.current_state_id:
        raise HTTPException(status_code=400, detail="Already in that state")

    dest = await db.get(State, to_state_id)
    if dest is None:
        raise HTTPException(status_code=404, detail="Destination state not found")

    # Travel is allowed without permit; permit gives 25% discount
    quote = quote_travel(character.current_state_id, to_state_id)
    cost = quote["cost"]
    if await _has_travel_permit(db, character, to_state_id):
        cost = round(cost * 0.75, 2)

    # High heat: security holds at border
    if character.heat >= 60:
        raise HTTPException(
            status_code=403,
            detail="Travel denied: security alert (heat too high)",
        )

    if character.cash < cost:
        raise HTTPException(status_code=400, detail="Insufficient funds for travel")

    now = utcnow()
    arrives = now + timedelta(minutes=quote["minutes"])
    character.cash -= cost
    character.is_traveling = True
    character.travel_until = arrives
    character.travel_destination_id = to_state_id

    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.TRAVEL,
        status=ActivityStatus.IN_PROGRESS,
        title=f"Travel to {dest.name}",
        description=f"In transit to {dest.capital}",
        age_gain_years=0,
        cash_delta=-cost,
        started_at=now,
        completes_at=arrives,
        ref_type="state",
        ref_id=to_state_id,
    )
    db.add(activity)
    await db.flush()
    from app.services.notify_service import broadcast_activity, broadcast_character

    await broadcast_activity(activity)
    await broadcast_character(character)

    log = TravelLog(
        character_id=character.id,
        from_state_id=character.current_state_id,
        to_state_id=to_state_id,
        cost=cost,
        started_at=now,
        arrives_at=arrives,
        activity_id=activity.id,
    )
    db.add(log)
    await db.flush()

    return {
        "from_state_id": log.from_state_id,
        "to_state_id": to_state_id,
        "to_state_name": dest.name,
        "cost": cost,
        "minutes": quote["minutes"],
        "arrives_at": arrives.isoformat(),
        "cash": round(character.cash, 2),
        "is_traveling": True,
    }
