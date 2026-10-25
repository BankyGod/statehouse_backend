from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.models.state import State
from app.models.user import User
from app.schemas.character import CharacterCreate
from app.services.tick_service import ensure_not_traveling, tick_character


async def get_character_for_user(
    db: AsyncSession, user: User, *, load_states: bool = False
) -> Character:
    stmt = select(Character).where(Character.user_id == user.id)
    if load_states:
        stmt = stmt.options(
            selectinload(Character.home_state),
            selectinload(Character.current_state),
        )
    result = await db.execute(stmt)
    character = result.scalar_one_or_none()
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create a character first",
        )
    await tick_character(db, character)
    return character


async def create_character(
    db: AsyncSession, user: User, payload: CharacterCreate
) -> Character:
    existing = await db.execute(select(Character).where(Character.user_id == user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Character already exists")

    name_taken = await db.execute(
        select(Character).where(Character.display_name == payload.display_name)
    )
    if name_taken.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Display name taken")

    state = await db.get(State, payload.home_state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")
    if not state.is_open or state.population_count >= state.population_cap:
        raise HTTPException(status_code=400, detail="State is full or closed")

    settings = get_settings()
    now = utcnow()
    character = Character(
        user_id=user.id,
        display_name=payload.display_name,
        home_state_id=state.id,
        current_state_id=state.id,
        home_state_locked=False,
        home_state_chosen_at=now,
        age_years=float(settings.starting_age),
        cash=settings.starting_cash + state.starting_bonus,
        bio=payload.bio,
        last_energy_at=now,
        last_heat_tick_at=now,
        last_health_at=now,
        last_nerve_at=now,
        health=100,
        max_health=100,
        nerve=20,
        max_nerve=20,
        strength=10.0,
        defense=10.0,
        speed=10.0,
        dexterity=10.0,
    )
    state.population_count += 1
    if state.population_count >= state.population_cap:
        state.is_open = False

    db.add(character)
    await db.flush()

    from app.services import housing_service

    await housing_service.assign_starter_hostel(db, character)
    await db.refresh(character)
    return character


async def reset_home_state(
    db: AsyncSession, character: Character, new_state_id: int
) -> Character:
    settings = get_settings()
    if character.home_state_locked:
        raise HTTPException(status_code=400, detail="Home state is permanently locked")

    deadline = character.home_state_chosen_at + timedelta(
        days=settings.home_state_reset_days
    )
    if utcnow() > deadline:
        character.home_state_locked = True
        raise HTTPException(
            status_code=400,
            detail=f"Home state reset window ({settings.home_state_reset_days} days) has closed",
        )

    if new_state_id == character.home_state_id:
        raise HTTPException(status_code=400, detail="Already your home state")

    new_state = await db.get(State, new_state_id)
    if new_state is None:
        raise HTTPException(status_code=404, detail="State not found")
    if not new_state.is_open or new_state.population_count >= new_state.population_cap:
        raise HTTPException(status_code=400, detail="Target state is full or closed")

    old_state = await db.get(State, character.home_state_id)
    if old_state:
        old_state.population_count = max(0, old_state.population_count - 1)
        if old_state.population_count < old_state.population_cap:
            old_state.is_open = True

    new_state.population_count += 1
    if new_state.population_count >= new_state.population_cap:
        new_state.is_open = False

    character.home_state_id = new_state.id
    character.current_state_id = new_state.id
    character.home_state_locked = True  # one-time reset
    await db.flush()
    await db.refresh(character)
    return character


def ensure_not_jailed(character: Character) -> None:
    if character.is_jailed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"You are in jail until "
                f"{character.jail_until.isoformat() if character.jail_until else 'unknown'}"
            ),
        )


def ensure_energy(character: Character, cost: int) -> None:
    if character.energy < cost:
        raise HTTPException(status_code=400, detail="Not enough energy")


def ensure_not_hospitalized(character: Character) -> None:
    if character.is_hospitalized:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are in hospital"
                + (
                    f" until {character.hospital_until.isoformat()}"
                    if character.hospital_until
                    else ""
                )
            ),
        )


def ensure_can_act(character: Character) -> None:
    ensure_not_jailed(character)
    ensure_not_traveling(character)
    ensure_not_hospitalized(character)
