"""Automated NPC citizens — real Character rows that live in states and act.

They use the same job / travel / chat / crime / gym / bank services as players
so the world feels populated even with few humans online.
"""

from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.core.security import hash_password
from app.models.character import Character
from app.models.crime import CrimeType
from app.models.job import Job
from app.models.state import State
from app.models.user import User
from app.services import (
    bank_service,
    crime_service,
    education_service,
    job_service,
    tick_service,
    travel_service,
)
from app.services.gym_service import train as gym_train

FIRST_NAMES = [
    "Kofi", "Ama", "Yaw", "Abena", "Kwesi", "Efua", "Kojo", "Akosua",
    "Ibrahim", "Fatima", "Omar", "Nadia", "Daniel", "Grace", "Samuel",
    "Ruth", "Joseph", "Helen", "Leroy", "Priya", "Marcus", "Claire",
    "Ethan", "Victoria", "Tunde", "Zainab", "Nana", "Sofia", "Raj",
    "Nora", "Adaeze", "Bankole", "Selorm", "Mariam", "Patrick", "Elena",
]

LAST_NAMES = [
    "Mensah", "Owusu", "Addo", "Boateng", "Asante", "Diallo", "Traore",
    "Nkrumah", "Okoro", "Quaye", "Tetteh", "Sarpong", "Frimpong", "Ba",
    "Cole", "Hale", "Frost", "Patel", "Berg", "Nwosu", "Lambert",
    "Mendes", "Bakare", "Yusuf", "Ampofo", "Rahman", "Darko", "Adjei",
]

CHAT_LINES = [
    "Anyone hiring in {state} right now?",
    "Just finished a shift. Energy's low.",
    "Coffee at the capital square later?",
    "Heard rents went up again…",
    "Train to Port Meridian looks packed today.",
    "Market prices are wild this morning.",
    "Who's watching the election results?",
    "Gym after work if anyone's free.",
    "Stay safe out there - heat's climbing in some districts.",
    "Proud to call {state} home.",
    "Looking for a clean job, no drama.",
    "Bank just paid a bit of interest. Nice.",
    "Traffic near the border checkpoint again.",
    "Parliament debate was loud today.",
    "New faces in town - welcome.",
]

# Reused so seeding hundreds of bots isn't bcrypt-bound
_BOT_HASH: str | None = None


def _bot_password_hash() -> str:
    global _BOT_HASH
    if _BOT_HASH is None:
        _BOT_HASH = hash_password("npc-bot-internal-only")
    return _BOT_HASH


def _npc_target_for_state(state: State) -> int:
    settings = get_settings()
    base = settings.npc_per_state
    # Slightly more NPCs in bigger / richer states
    bonus = min(8, max(0, (state.population_cap - 300) // 50))
    return base + bonus


def _unique_name(used: set[str], state_slug: str, idx: int) -> str:
    for _ in range(40):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name
    name = f"Citizen {state_slug.title().replace('-', '')}{idx}"
    used.add(name)
    return name


async def ensure_npc_citizens(db: AsyncSession) -> dict:
    """Idempotent: fill each state up to its NPC target with real Character rows.

    Commits per state so Neon seeding stays fast and restart-safe.
    """
    settings = get_settings()
    if not settings.npc_sim_enabled:
        return {"created": 0, "skipped": True}

    states = list((await db.execute(select(State).order_by(State.id))).scalars().all())
    existing_names = {
        n
        for n in (
            await db.execute(select(Character.display_name))
        ).scalars().all()
    }
    existing_usernames = {
        u
        for u in (await db.execute(select(User.username))).scalars().all()
    }
    created = 0
    now = utcnow()
    pwd = _bot_password_hash()

    for state in states:
        target = _npc_target_for_state(state)
        current = (
            await db.execute(
                select(func.count())
                .select_from(Character)
                .where(
                    Character.is_npc.is_(True),
                    Character.home_state_id == state.id,
                )
            )
        ).scalar_one()
        need = max(0, target - int(current))
        if need == 0:
            if state.npc_population_count != current:
                state.npc_population_count = int(current)
                await db.flush()
            continue

        # Find next free username index for this state (handles partial seeds)
        prefix = f"npc_{state.slug.replace('-', '_')}_"
        next_idx = 1
        for uname in existing_usernames:
            if uname.startswith(prefix):
                suffix = uname[len(prefix) :]
                if suffix.isdigit():
                    next_idx = max(next_idx, int(suffix) + 1)

        for i in range(need):
            idx = next_idx + i
            display = _unique_name(existing_names, state.slug, idx)
            username = f"{prefix}{idx}"
            if username in existing_usernames:
                continue
            existing_usernames.add(username)
            email = f"{username}@npc.statehouse.local"

            user = User(
                email=email,
                username=username,
                hashed_password=pwd,
                is_active=True,
                is_bot=True,
            )
            db.add(user)
            await db.flush()

            character = Character(
                user_id=user.id,
                display_name=display,
                home_state_id=state.id,
                current_state_id=state.id,
                home_state_locked=True,
                home_state_chosen_at=now,
                age_years=float(random.randint(19, 55)),
                cash=round(random.uniform(80, 600), 2),
                bank_balance=round(random.uniform(0, 400), 2),
                energy=random.randint(40, 100),
                max_energy=100,
                base_max_energy=100,
                reputation=random.randint(0, 25),
                heat=0.0,
                bio=f"Local of {state.name}.",
                is_npc=True,
                npc_next_action_at=now
                + timedelta(seconds=random.randint(5, 90)),
                last_energy_at=now,
                last_heat_tick_at=now,
                last_health_at=now,
                last_nerve_at=now,
                last_bank_interest_at=now,
                health=100,
                max_health=100,
                nerve=20,
                max_nerve=20,
                strength=round(random.uniform(8, 18), 1),
                defense=round(random.uniform(8, 18), 1),
                speed=round(random.uniform(8, 18), 1),
                dexterity=round(random.uniform(8, 18), 1),
                # Hostel skipped for seed speed — still countable citizens
                is_homeless=False,
            )
            db.add(character)
            created += 1

        await db.flush()
        new_count = (
            await db.execute(
                select(func.count())
                .select_from(Character)
                .where(
                    Character.is_npc.is_(True),
                    Character.home_state_id == state.id,
                )
            )
        ).scalar_one()
        state.npc_population_count = int(new_count)
        await db.commit()

    return {"created": created, "states": len(states)}


async def _has_job(db: AsyncSession, character_id: int) -> bool:
    result = await db.execute(
        select(Job.id).where(
            Job.character_id == character_id,
            Job.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none() is not None


async def _action_work_or_hire(db: AsyncSession, character: Character) -> str:
    if await _has_job(db, character.id):
        await job_service.work_shift(db, character)
        return "work"
    listings = await job_service.list_jobs_in_state(db, character.current_state_id)
    # Prefer low education jobs
    listings = sorted(listings, key=lambda L: L.min_education_level)
    for listing in listings[:8]:
        try:
            await job_service.hire(db, character, listing.id)
            return "hire"
        except HTTPException:
            continue
    return "idle"


async def _action_chat(db: AsyncSession, character: Character) -> str:
    state = await db.get(State, character.current_state_id)
    name = state.name if state else "town"
    body = random.choice(CHAT_LINES).format(state=name)
    # Bypass human cooldown by posting with ensure_can_act only — temporarily
    # lower cooldown via direct insert path reused from chat_service
    from app.models.chat import ChatMessage
    from app.realtime import emit_chat

    now = utcnow()
    msg = ChatMessage(
        state_id=character.current_state_id,
        character_id=character.id,
        display_name=character.display_name,
        body=body,
        posted_at=now,
    )
    db.add(msg)
    await db.flush()
    payload = {
        "id": msg.id,
        "state_id": msg.state_id,
        "character_id": msg.character_id,
        "display_name": msg.display_name,
        "body": msg.body,
        "posted_at": msg.posted_at,
    }
    try:
        await emit_chat(payload)
    except Exception:
        pass
    return "chat"


async def _action_study(db: AsyncSession, character: Character) -> str:
    from app.models.education import EducationEnrollment, EducationProgram, EnrollmentStatus

    active = await db.execute(
        select(EducationEnrollment.id).where(
            EducationEnrollment.character_id == character.id,
            EducationEnrollment.status == EnrollmentStatus.ENROLLED,
        )
    )
    if active.scalar_one_or_none():
        return "idle"
    await education_service.ensure_education_seeded(db)
    programs = list(
        (
            await db.execute(
                select(EducationProgram)
                .where(
                    EducationProgram.is_active.is_(True),
                    EducationProgram.cost <= character.cash,
                    EducationProgram.min_education_level <= 1,
                )
                .limit(40)
            )
        )
        .scalars()
        .all()
    )
    if not programs:
        return "idle"
    program = random.choice(programs)
    await education_service.enroll_in_program(db, character, program.id)
    return "study"


async def _action_travel(db: AsyncSession, character: Character) -> str:
    from app.models.transport import TransportCarrier

    states = list((await db.execute(select(State.id))).scalars().all())
    options = [s for s in states if s != character.current_state_id]
    if not options:
        return "idle"
    dest = random.choice(options)
    # Prefer going home sometimes
    if character.current_state_id != character.home_state_id and random.random() < 0.55:
        dest = character.home_state_id
    if character.cash < 40:
        return "idle"
    await travel_service.ensure_carriers_seeded(db)
    carriers = list(
        (
            await db.execute(
                select(TransportCarrier.id).where(TransportCarrier.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    carrier_id = random.choice(carriers) if carriers else None
    await travel_service.start_travel(db, character, dest, carrier_id=carrier_id)
    return "travel"


async def _action_crime(db: AsyncSession, character: Character) -> str:
    # Stick to lowest-risk street theft
    await crime_service.commit_crime(db, character, CrimeType.STREET_THEFT)
    return "crime"


async def _action_gym(db: AsyncSession, character: Character) -> str:
    stat = random.choice(["strength", "defense", "speed", "dexterity"])
    await gym_train(db, character, stat)
    return "gym"


async def _action_bank(db: AsyncSession, character: Character) -> str:
    if character.cash >= 80:
        amount = round(min(character.cash * 0.4, 120), 2)
        await bank_service.deposit(db, character, amount)
        return "deposit"
    if character.bank_balance >= 40:
        amount = round(min(character.bank_balance * 0.3, 60), 2)
        await bank_service.withdraw(db, character, amount)
        return "withdraw"
    return "idle"


async def _pick_and_act(db: AsyncSession, character: Character) -> str:
    weights = [
        ("work", 38),
        ("chat", 22),
        ("gym", 12),
        ("bank", 10),
        ("travel", 8),
        ("study", 4),
        ("crime", 5),
        ("idle", 3),
    ]
    # Unemployed NPCs bias toward hire/work
    if not await _has_job(db, character.id):
        weights = [("work", 55), ("chat", 20), ("travel", 8), ("bank", 7), ("idle", 10)]

    actions, probs = zip(*weights)
    pick = random.choices(actions, weights=probs, k=1)[0]

    try:
        if pick == "work":
            return await _action_work_or_hire(db, character)
        if pick == "chat":
            return await _action_chat(db, character)
        if pick == "travel":
            return await _action_travel(db, character)
        if pick == "study":
            return await _action_study(db, character)
        if pick == "crime":
            return await _action_crime(db, character)
        if pick == "gym":
            return await _action_gym(db, character)
        if pick == "bank":
            return await _action_bank(db, character)
    except HTTPException:
        return "blocked"
    except Exception:
        return "error"
    return "idle"


async def run_npc_sim_batch(db: AsyncSession) -> dict:
    """Tick due NPCs and run one life action each (capped batch)."""
    settings = get_settings()
    if not settings.npc_sim_enabled:
        return {"acted": 0}

    now = utcnow()
    result = await db.execute(
        select(Character)
        .where(
            Character.is_npc.is_(True),
            Character.is_jailed.is_(False),
            Character.is_hospitalized.is_(False),
            (Character.npc_next_action_at.is_(None))
            | (Character.npc_next_action_at <= now),
        )
        .order_by(Character.npc_next_action_at.nulls_first())
        .limit(settings.npc_sim_batch_size)
    )
    npcs = list(result.scalars().all())
    acted = 0
    actions: dict[str, int] = {}

    for character in npcs:
        # Lightweight regen / travel arrival only (skip world elections tick)
        from app.services import (
            crime_service,
            education_service,
            health_service,
        )

        from app.services import bank_service, housing_service

        await health_service.discharge_if_due(character)
        tick_service.apply_energy_regen(character)
        crime_service.apply_nerve_regen(character)
        tick_service.apply_heat_decay(character)
        health_service.apply_health_regen(character)
        await tick_service.complete_due_travel(db, character)
        await education_service.complete_due_education(db, character)
        await housing_service.process_rent(db, character)
        await bank_service.apply_savings_interest(db, character)

        if character.is_traveling or character.is_jailed or character.is_hospitalized:
            character.npc_next_action_at = now + timedelta(
                seconds=random.randint(30, 120)
            )
            continue

        kind = await _pick_and_act(db, character)
        actions[kind] = actions.get(kind, 0) + 1
        acted += 1
        character.npc_next_action_at = now + timedelta(
            seconds=random.randint(25, 140)
        )

    await db.flush()
    # World systems still advance occasionally without depending on player online
    await tick_service.tick_world_if_due(db)
    return {"acted": acted, "actions": actions}


_sim_task: asyncio.Task | None = None


async def npc_sim_loop() -> None:
    """Background driver — keeps United Amir feeling inhabited."""
    from app.core.database import get_session_factory

    settings = get_settings()
    # Stagger first run so seed finishes
    await asyncio.sleep(8)
    while True:
        try:
            if settings.npc_sim_enabled:
                factory = get_session_factory()
                async with factory() as db:
                    summary = await run_npc_sim_batch(db)
                    await db.commit()
                    if summary.get("acted"):
                        print(f"NPC sim: {summary}", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"NPC sim error: {exc}")
        await asyncio.sleep(get_settings().npc_sim_interval_seconds)


def start_npc_sim_loop() -> asyncio.Task | None:
    global _sim_task
    if not get_settings().npc_sim_enabled:
        return None
    if _sim_task and not _sim_task.done():
        return _sim_task
    _sim_task = asyncio.create_task(npc_sim_loop(), name="npc-sim")
    return _sim_task


async def stop_npc_sim_loop() -> None:
    global _sim_task
    if _sim_task and not _sim_task.done():
        _sim_task.cancel()
        try:
            await _sim_task
        except asyncio.CancelledError:
            pass
    _sim_task = None
