from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.models.medical import MedicalVisit, TreatmentType
from app.models.state import State
from app.services.character_service import (
    ensure_can_act,
    ensure_not_hospitalized,
    ensure_not_jailed,
)
from app.services.tick_service import ensure_not_traveling


def apply_damage(
    character: Character, amount: int, condition: str | None = None
) -> int:
    """Reduce HP; return actual damage dealt. Auto-hospitalize at 0."""
    if amount <= 0:
        return 0
    before = character.health
    character.health = max(0, character.health - amount)
    if condition:
        character.condition = condition
    if character.health <= 0:
        _force_hospital(character, hours=6.0, condition=condition or "critical")
    return before - character.health


def _force_hospital(
    character: Character, hours: float, condition: str = "injured"
) -> None:
    now = utcnow()
    character.is_hospitalized = True
    character.hospital_until = now + timedelta(hours=hours)
    character.condition = condition
    # Cancel travel if somehow mid-trip
    character.is_traveling = False
    character.travel_until = None
    character.travel_destination_id = None


def apply_health_regen(character: Character) -> int:
    if character.is_hospitalized or character.health >= character.max_health:
        character.last_health_at = utcnow()
        return 0
    # Mild sickness: slower regen
    settings = get_settings()
    now = utcnow()
    last = character.last_health_at or now
    if last.tzinfo is None:
        from datetime import timezone

        last = last.replace(tzinfo=timezone.utc)

    interval = settings.health_regen_minutes * 60
    if character.condition:
        interval = int(interval * 1.5)

    elapsed = (now - last).total_seconds()
    if interval <= 0 or elapsed < interval:
        return 0

    gained = int(elapsed // interval)
    before = character.health
    character.health = min(character.max_health, character.health + gained)
    actual = character.health - before
    character.last_health_at = last + timedelta(seconds=actual * interval)
    if character.health >= character.max_health:
        character.last_health_at = now
        if character.condition in ("bruised", "exhausted"):
            character.condition = None
    return actual


async def discharge_if_due(character: Character) -> bool:
    if not character.is_hospitalized or not character.hospital_until:
        return False
    until = character.hospital_until
    if until.tzinfo is None:
        from datetime import timezone

        until = until.replace(tzinfo=timezone.utc)
    if until > utcnow():
        return False

    character.is_hospitalized = False
    character.hospital_until = None
    character.health = max(character.health, int(character.max_health * 0.6))
    character.condition = None
    character.last_health_at = utcnow()
    return True


async def clinic_heal(
    db: AsyncSession, character: Character, hp_amount: int
) -> dict:
    """Instant partial heal at a clinic — cash only, must be free to act."""
    ensure_can_act(character)
    ensure_not_hospitalized(character)
    if hp_amount <= 0:
        raise HTTPException(status_code=400, detail="hp_amount must be positive")
    if character.health >= character.max_health:
        raise HTTPException(status_code=400, detail="Already at full health")

    settings = get_settings()
    need = min(hp_amount, character.max_health - character.health)
    cost = round(need * settings.clinic_heal_cost_per_hp, 2)
    # Crystal Springs / capital clinics slightly cheaper
    state = await db.get(State, character.current_state_id)
    if state and state.slug in ("crystal-springs", "amira-central", "scholars-haven"):
        cost = round(cost * 0.85, 2)

    if character.cash < cost:
        raise HTTPException(status_code=400, detail="Insufficient funds for clinic")

    before = character.health
    character.cash -= cost
    character.health = min(character.max_health, character.health + need)
    if character.health >= character.max_health:
        character.condition = None
    character.last_health_at = utcnow()

    visit = MedicalVisit(
        character_id=character.id,
        state_id=character.current_state_id,
        treatment_type=TreatmentType.CLINIC,
        hp_before=before,
        hp_after=character.health,
        cost=cost,
        hours=0,
        notes="Walk-in clinic",
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    db.add(visit)
    await db.flush()
    return {
        "treatment": "clinic",
        "hp_healed": character.health - before,
        "health": character.health,
        "cost": cost,
        "condition": character.condition,
        "cash": round(character.cash, 2),
    }


async def hospitalize(db: AsyncSession, character: Character) -> dict:
    """Full hospital stay — blocks actions until discharged."""
    ensure_not_jailed(character)
    ensure_not_traveling(character)
    if character.is_hospitalized:
        raise HTTPException(status_code=400, detail="Already hospitalized")
    if character.health >= character.max_health and not character.condition:
        raise HTTPException(status_code=400, detail="You don't need hospital care")

    settings = get_settings()
    missing = character.max_health - character.health
    hours = settings.hospital_base_hours + (missing / 25.0)
    # Medical hubs faster
    state = await db.get(State, character.current_state_id)
    if state and state.slug in ("crystal-springs", "amira-central"):
        hours *= 0.75

    cost = round(40 + missing * 1.5, 2)
    if character.cash < cost:
        raise HTTPException(status_code=400, detail="Insufficient funds for hospital")

    before = character.health
    character.cash -= cost
    now = utcnow()
    character.is_hospitalized = True
    character.hospital_until = now + timedelta(hours=hours)
    character.condition = character.condition or "recovering"

    visit = MedicalVisit(
        character_id=character.id,
        state_id=character.current_state_id,
        treatment_type=TreatmentType.HOSPITAL,
        hp_before=before,
        hp_after=before,  # restored on discharge
        cost=cost,
        hours=hours,
        notes="Admitted",
        started_at=now,
    )
    db.add(visit)
    await db.flush()
    return {
        "treatment": "hospital",
        "cost": cost,
        "hours": round(hours, 2),
        "hospital_until": character.hospital_until.isoformat(),
        "health": character.health,
        "cash": round(character.cash, 2),
        "message": f"Admitted for {hours:.1f} hours. Actions locked until discharge.",
    }
