"""Create tester account President / leader and install as national president.

Also grants presidential credentials and activates any pending businesses.

Usage:
  python scripts/seed_president.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import configure_engine, get_session_factory  # noqa: E402
from app.core.game_time import utcnow  # noqa: E402
from app.core.security import hash_password  # noqa: E402
import app.models  # noqa: F401, E402
from app.models.business import Business, BusinessStatus  # noqa: E402
from app.models.character import Character  # noqa: E402
from app.models.education import (  # noqa: E402
    EDUCATION_CATALOG,
    EducationEnrollment,
    EducationTrack,
    EnrollmentStatus,
)
from app.models.state import State  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.politics_service import get_or_create_nation  # noqa: E402

USERNAME = "president"
PASSWORD = "leader"
EMAIL = "president@unitedamir.com"
DISPLAY_NAME = "President"

# Credentials a sitting head of state would plausibly hold
PRESIDENT_DEGREES: list[tuple[EducationTrack, str]] = [
    (EducationTrack.DIPLOMA, "Diploma in Public Administration"),
    (EducationTrack.BACHELORS, "Bachelor's in Political Science"),
    (EducationTrack.BACHELORS, "Bachelor's in Economics"),
    (EducationTrack.LAW, "Bachelor of Laws (LLB)"),
    (EducationTrack.MASTERS, "Master of Public Policy (MPP)"),
    (EducationTrack.SHORT_COURSE, "Certificate in Constitutional Governance"),
]


async def _ensure_credentials(db, character: Character) -> list[str]:
    """Idempotently grant completed presidential degrees by title."""
    existing = await db.execute(
        select(EducationEnrollment.title).where(
            EducationEnrollment.character_id == character.id,
            EducationEnrollment.status == EnrollmentStatus.COMPLETED,
        )
    )
    have = {t for (t,) in existing.all()}
    now = utcnow()
    added: list[str] = []
    for track, title in PRESIDENT_DEGREES:
        if title in have:
            continue
        meta = EDUCATION_CATALOG[track]
        started = now - timedelta(days=meta["real_days"] + 90)
        completed = started + timedelta(days=meta["real_days"])
        db.add(
            EducationEnrollment(
                character_id=character.id,
                track=track,
                status=EnrollmentStatus.COMPLETED,
                title=title,
                cost_paid=meta["cost"],
                age_gain_years=meta["age_years"],
                education_level=meta["level"],
                started_at=started,
                completes_at=completed,
                completed_at=completed,
            )
        )
        added.append(title)
    if added:
        await db.flush()
    return added


async def _activate_pending_businesses(db, character: Character) -> list[str]:
    """Force-approve any pending registrations for this character."""
    now = utcnow()
    result = await db.execute(
        select(Business).where(
            Business.owner_id == character.id,
            Business.status == BusinessStatus.PENDING,
        )
    )
    names: list[str] = []
    for biz in result.scalars().all():
        biz.status = BusinessStatus.ACTIVE
        biz.registered_at = now
        biz.registration_completes_at = now
        biz.last_ops_at = now
        biz.last_payroll_at = now
        names.append(biz.name)
    if names:
        await db.flush()
    return names


async def main() -> None:
    engine = configure_engine()
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(User).where(User.username == USERNAME))
        user = result.scalar_one_or_none()
        created_user = False
        if user is None:
            user = User(
                email=EMAIL,
                username=USERNAME,
                hashed_password=hash_password(PASSWORD),
            )
            db.add(user)
            await db.flush()
            created_user = True
        else:
            user.hashed_password = hash_password(PASSWORD)
            user.is_active = True

        char_result = await db.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = char_result.scalar_one_or_none()
        created_character = False
        if character is None:
            state_result = await db.execute(
                select(State).where(State.slug == "amira-central")
            )
            state = state_result.scalar_one_or_none()
            if state is None:
                state_result = await db.execute(select(State).order_by(State.id).limit(1))
                state = state_result.scalar_one()

            name_taken = await db.execute(
                select(Character).where(Character.display_name == DISPLAY_NAME)
            )
            display = DISPLAY_NAME
            if name_taken.scalar_one_or_none() is not None:
                display = "President of United Amir"

            now = utcnow()
            character = Character(
                user_id=user.id,
                display_name=display,
                home_state_id=state.id,
                current_state_id=state.id,
                home_state_locked=False,
                home_state_chosen_at=now,
                age_years=45.0,
                cash=5000.0,
                bank_balance=10000.0,
                bio="Sitting President of United Amir.",
                last_energy_at=now,
                last_heat_tick_at=now,
                last_health_at=now,
                last_nerve_at=now,
                health=100,
                max_health=100,
                nerve=20,
                max_nerve=20,
                strength=12.0,
                defense=12.0,
                speed=12.0,
                dexterity=12.0,
                reputation=50,
                energy=100,
                max_energy=100,
                is_npc=False,
            )
            db.add(character)
            state.population_count = int(state.population_count or 0) + 1
            await db.flush()
            created_character = True
        else:
            character.age_years = max(float(character.age_years or 0), 45.0)
            character.is_npc = False
            if character.display_name != DISPLAY_NAME:
                taken = await db.execute(
                    select(Character).where(
                        Character.display_name == DISPLAY_NAME,
                        Character.id != character.id,
                    )
                )
                if taken.scalar_one_or_none() is None:
                    character.display_name = DISPLAY_NAME

        nation = await get_or_create_nation(db)
        nation.president_character_id = character.id
        nation.president_npc_name = character.display_name
        nation.notes = "Tester installed as sitting president."

        degrees_added = await _ensure_credentials(db, character)
        businesses_activated = await _activate_pending_businesses(db, character)

        await db.commit()

        print("President account ready")
        print(f"  username:     {USERNAME}  (login also accepts President)")
        print(f"  password:     {PASSWORD}")
        print(f"  display_name: {character.display_name}")
        print(f"  character_id: {character.id}")
        print(f"  user_created: {created_user}")
        print(f"  char_created: {created_character}")
        print(f"  nation.president_character_id: {nation.president_character_id}")
        print(f"  degrees_added: {len(degrees_added)}")
        for title in degrees_added:
            print(f"    + {title}")
        print(f"  businesses_activated: {len(businesses_activated)}")
        for name in businesses_activated:
            print(f"    + {name} -> active")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
