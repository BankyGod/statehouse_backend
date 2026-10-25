from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.services import notify_service


def _seconds_remaining(until) -> int:
    if until is None:
        return 0
    now = utcnow()
    if until.tzinfo is None:
        from datetime import timezone

        until = until.replace(tzinfo=timezone.utc)
    return max(0, int((until - now).total_seconds()))


def jail_status(character: Character) -> dict:
    settings = get_settings()
    seconds = _seconds_remaining(character.jail_until) if character.is_jailed else 0
    hours_left = seconds / 3600.0
    bail = round(hours_left * settings.jail_bail_per_hour, 2) if seconds else 0.0
    return {
        "is_jailed": character.is_jailed,
        "jail_until": character.jail_until,
        "seconds_remaining": seconds,
        "bail_cost": bail,
        "heat": character.heat,
    }


def hospital_status(character: Character) -> dict:
    settings = get_settings()
    seconds = (
        _seconds_remaining(character.hospital_until)
        if character.is_hospitalized
        else 0
    )
    return {
        "is_hospitalized": character.is_hospitalized,
        "hospital_until": character.hospital_until,
        "seconds_remaining": seconds,
        "health": character.health,
        "max_health": character.max_health,
        "condition": character.condition,
        "clinic_cost_per_hp": settings.clinic_heal_cost_per_hp,
    }


async def pay_bail(db: AsyncSession, character: Character) -> dict:
    if not character.is_jailed:
        raise HTTPException(status_code=400, detail="You are not in jail")
    status = jail_status(character)
    cost = status["bail_cost"]
    if cost <= 0:
        character.is_jailed = False
        character.jail_until = None
        await db.flush()
        return {"bailed": True, "paid": 0.0, "cash": character.cash}
    if character.cash < cost and character.bank_balance < cost:
        raise HTTPException(
            status_code=400,
            detail=f"Need ${cost:.2f} cash or bank to bail out",
        )
    paid = cost
    if character.cash >= cost:
        character.cash = round(character.cash - cost, 2)
    else:
        character.bank_balance = round(character.bank_balance - cost, 2)
    character.is_jailed = False
    character.jail_until = None
    character.heat = min(100.0, character.heat + 5.0)
    await notify_service.push(
        db,
        character.id,
        "Released on bail",
        body=f"Paid ${paid:.2f}. Heat +5.",
        category="jail",
    )
    await db.flush()
    return {
        "bailed": True,
        "paid": paid,
        "cash": character.cash,
        "bank_balance": character.bank_balance,
        "heat": character.heat,
    }
