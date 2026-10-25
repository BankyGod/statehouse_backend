from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.activity import ActivityType
from app.models.character import Character
from app.models.item import InventoryItem
from app.services.character_service import ensure_can_act, ensure_energy
from app.services import notify_service

GYM_STATS = ("strength", "defense", "speed", "dexterity")


def catalog() -> list[dict]:
    settings = get_settings()
    return [
        {
            "stat": s,
            "energy_cost": settings.gym_energy_cost,
            "gain_base": settings.gym_gain_base,
            "label": s.capitalize(),
        }
        for s in GYM_STATS
    ]


async def _gym_bonus(db: AsyncSession, character_id: int) -> float:
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.character_id == character_id,
            InventoryItem.item_key == "training_weights",
            InventoryItem.quantity > 0,
        )
    )
    return 1.05 if result.scalar_one_or_none() else 1.0


async def train(db: AsyncSession, character: Character, stat: str) -> dict:
    ensure_can_act(character)
    if stat not in GYM_STATS:
        raise HTTPException(status_code=400, detail="Invalid gym stat")
    settings = get_settings()
    cost = settings.gym_energy_cost
    ensure_energy(character, cost)

    current = float(getattr(character, stat))
    # Soft diminishing returns
    diminishing = max(0.35, 1.0 - (current / 500.0))
    bonus = await _gym_bonus(db, character.id)
    event_mult = 1.0
    from app.services import social_service

    for event in await social_service.list_active_events(db):
        if event["effect_key"] == "gym_boost":
            event_mult = float(event["effect_value"])
    gain = round(settings.gym_gain_base * diminishing * bonus * event_mult, 3)

    character.energy -= cost
    character.last_energy_at = utcnow()
    setattr(character, stat, round(current + gain, 3))
    new_val = float(getattr(character, stat))

    await notify_service.log_instant_activity(
        db,
        character.id,
        ActivityType.OTHER,
        f"Gym: trained {stat}",
        description=f"+{gain} {stat} -> {new_val}",
        energy_cost=cost,
    )
    await db.flush()
    return {
        "stat": stat,
        "gained": gain,
        "new_value": new_val,
        "energy": character.energy,
        "strength": character.strength,
        "defense": character.defense,
        "speed": character.speed,
        "dexterity": character.dexterity,
    }
