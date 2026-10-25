"""Apply passive updates whenever a character is loaded."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus
from app.models.character import Character
from app.models.travel import TravelLog


def apply_energy_regen(character: Character) -> int:
    """Return energy points gained this tick."""
    settings = get_settings()
    now = utcnow()
    if character.energy >= character.max_energy:
        character.last_energy_at = now
        return 0

    last = character.last_energy_at or character.created_at or now
    if last.tzinfo is None:
        # sqlite sometimes returns naive datetimes
        from datetime import timezone

        last = last.replace(tzinfo=timezone.utc)

    elapsed = (now - last).total_seconds()
    interval = settings.energy_regen_minutes * 60
    if interval <= 0 or elapsed < interval:
        return 0

    gained = int(elapsed // interval)
    if gained <= 0:
        return 0

    before = character.energy
    character.energy = min(character.max_energy, character.energy + gained)
    actual = character.energy - before
    # Keep leftover partial interval
    character.last_energy_at = last + timedelta(seconds=actual * interval)
    if character.energy >= character.max_energy:
        character.last_energy_at = now
    return actual


def apply_heat_decay(character: Character) -> float:
    if character.heat <= 0 or character.is_jailed:
        character.last_heat_tick_at = utcnow()
        return 0.0

    settings = get_settings()
    now = utcnow()
    last = character.last_heat_tick_at or now
    if last.tzinfo is None:
        from datetime import timezone

        last = last.replace(tzinfo=timezone.utc)

    hours = (now - last).total_seconds() / 3600.0
    if hours <= 0:
        return 0.0

    decay = hours * settings.heat_decay_per_hour
    before = character.heat
    character.heat = max(0.0, character.heat - decay)
    character.last_heat_tick_at = now
    return before - character.heat


async def complete_due_travel(db: AsyncSession, character: Character) -> bool:
    if not character.is_traveling:
        return False
    if not character.travel_until:
        return False

    until = character.travel_until
    if until.tzinfo is None:
        from datetime import timezone

        until = until.replace(tzinfo=timezone.utc)

    if until > utcnow():
        return False

    now = utcnow()
    if character.travel_destination_id:
        character.current_state_id = character.travel_destination_id

    result = await db.execute(
        select(TravelLog).where(
            TravelLog.character_id == character.id,
            TravelLog.arrived_at.is_(None),
        )
    )
    for log in result.scalars().all():
        log.arrived_at = now
        if log.activity_id:
            activity = await db.get(Activity, log.activity_id)
            if activity:
                activity.status = ActivityStatus.COMPLETED
                activity.completed_at = now
                from app.services.notify_service import broadcast_activity

                await broadcast_activity(activity)

    character.is_traveling = False
    character.travel_until = None
    character.travel_destination_id = None
    from app.services import notify_service

    await notify_service.push(
        db,
        character.id,
        "Arrived",
        body="Your trip is complete.",
        category="travel",
    )
    return True


def ensure_not_traveling(character: Character) -> None:
    from fastapi import HTTPException

    if character.is_traveling:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are traveling"
                + (
                    f" until {character.travel_until.isoformat()}"
                    if character.travel_until
                    else ""
                )
            ),
        )


async def tick_character(db: AsyncSession, character: Character) -> Character:
    """Jail release, regen, heat decay, travel/education/business completion."""
    # Local imports avoid circular dependency with character_service
    from app.services import (
        bank_service,
        business_service,
        cabinet_service,
        crime_service,
        education_service,
        health_service,
        housing_service,
        legislation_service,
        politics_service,
    )

    now = utcnow()
    if character.is_jailed and character.jail_until:
        until = character.jail_until
        if until.tzinfo is None:
            from datetime import timezone

            until = until.replace(tzinfo=timezone.utc)
        if until <= now:
            character.is_jailed = False
            character.jail_until = None
            from app.services import notify_service

            await notify_service.push(
                db,
                character.id,
                "Released from jail",
                body="Your sentence is over.",
                category="jail",
            )

    await health_service.discharge_if_due(character)
    apply_energy_regen(character)
    crime_service.apply_nerve_regen(character)
    apply_heat_decay(character)
    health_service.apply_health_regen(character)
    await complete_due_travel(db, character)
    await education_service.complete_due_education(db, character)
    await business_service.activate_due_businesses(db, character)
    await business_service.process_business_ops(db, character)
    await housing_service.process_rent(db, character)
    await politics_service.advance_election_phases(db)
    await legislation_service.resolve_due_bills(db)
    await legislation_service.resolve_due_budgets(db)
    await cabinet_service.pay_minister_salaries(db)
    await bank_service.apply_savings_interest(db, character)
    await db.flush()
    try:
        from app.realtime import emit_character

        await emit_character(character)
    except Exception:
        pass
    return character
