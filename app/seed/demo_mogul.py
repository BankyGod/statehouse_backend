"""Seed a ready-made advanced account for testing / FE demos."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.core.security import hash_password
from app.models.business import Business, BusinessStatus
from app.models.character import Character
from app.models.education import (
    EDUCATION_CATALOG,
    EducationEnrollment,
    EducationTrack,
    EnrollmentStatus,
)
from app.models.employee import EmployeeRole
from app.models.state import State
from app.models.user import User
from app.services import employee_service, housing_service

DEMO_USERNAME = "mogul"
DEMO_PASSWORD = "password123"
DEMO_EMAIL = "mogul@unitedamir.com"
DEMO_DISPLAY = "TycoonBanky"

# 4 degrees + 1 master's (custom titles)
DEMO_DEGREES = [
    (EducationTrack.BACHELORS, "Bachelor's in Business Administration"),
    (EducationTrack.BACHELORS, "Bachelor's in Computer Science"),
    (EducationTrack.BACHELORS, "Bachelor's in Economics"),
    (EducationTrack.LAW, "Bachelor of Laws (LLB)"),
    (EducationTrack.MASTERS, "Master of Business Administration (MBA)"),
]

STAFF_ROSTER: list[tuple[str, EmployeeRole]] = [
    # Floor / ops
    ("Kwesi Mensah", EmployeeRole.LABOURER),
    ("Ama Boateng", EmployeeRole.LABOURER),
    ("Ibrahim Sule", EmployeeRole.LABOURER),
    ("Efua Darko", EmployeeRole.LABOURER),
    ("Yaw Owusu", EmployeeRole.LABOURER),
    ("Elena Frost", EmployeeRole.LABOURER),
    ("Amina Diallo", EmployeeRole.LABOURER),
    ("Tunde Bakare", EmployeeRole.LABOURER),
    ("Nana Serwaa", EmployeeRole.LABOURER),
    ("Patrick Osei", EmployeeRole.LABOURER),
    ("Linda Frimpong", EmployeeRole.LABOURER),
    ("Jacob Mensah", EmployeeRole.LABOURER),
    # Admin
    ("Nadia Traore", EmployeeRole.CLERK),
    ("Kofi Adjei", EmployeeRole.CLERK),
    ("Grace Addo", EmployeeRole.CLERK),
    ("Samuel Tetteh", EmployeeRole.CLERK),
    ("Joseph Addai", EmployeeRole.CLERK),
    ("Mariam Ba", EmployeeRole.CLERK),
    ("Chris Lambert", EmployeeRole.CLERK),
    ("Zainab Yusuf", EmployeeRole.CLERK),
    # Specialists
    ("Priya Nkrumah", EmployeeRole.SPECIALIST),
    ("Daniel Okoro", EmployeeRole.SPECIALIST),
    ("Helen Quaye", EmployeeRole.SPECIALIST),
    ("Omar Diallo", EmployeeRole.SPECIALIST),
    ("Victoria Okeke", EmployeeRole.SPECIALIST),
    ("Ethan Cole", EmployeeRole.SPECIALIST),
    ("Sofia Mendes", EmployeeRole.SPECIALIST),
    ("Raj Patel", EmployeeRole.SPECIALIST),
    ("Nora Berg", EmployeeRole.SPECIALIST),
    # Management
    ("Ruth Asante", EmployeeRole.MANAGER),
    ("Marcus Hale", EmployeeRole.MANAGER),
    ("Fatima Rahman", EmployeeRole.MANAGER),
    ("Bankole Sarpong", EmployeeRole.MANAGER),
    ("Adaeze Nwosu", EmployeeRole.MANAGER),
    ("Tom Hughes", EmployeeRole.MANAGER),
    # C-suite
    ("Leroy Banks", EmployeeRole.EXECUTIVE),
    ("Claire Mensah", EmployeeRole.EXECUTIVE),
    ("Isabel Cruz", EmployeeRole.EXECUTIVE),
    ("David Okonkwo", EmployeeRole.EXECUTIVE),
]


async def seed_demo_mogul(db: AsyncSession) -> dict:
    existing = await db.execute(select(User).where(User.username == DEMO_USERNAME))
    if existing.scalar_one_or_none() is not None:
        return {"created": False, "username": DEMO_USERNAME, "password": DEMO_PASSWORD}

    state_result = await db.execute(
        select(State).where(State.slug == "amira-central")
    )
    state = state_result.scalar_one_or_none()
    if state is None:
        state_result = await db.execute(select(State).order_by(State.id).limit(1))
        state = state_result.scalar_one()

    now = utcnow()
    user = User(
        email=DEMO_EMAIL,
        username=DEMO_USERNAME,
        hashed_password=hash_password(DEMO_PASSWORD),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Age from degrees: 4+4+4+2+2 = 16 → start 18 + 16 = 34
    age = 18.0
    for track, _ in DEMO_DEGREES:
        age += EDUCATION_CATALOG[track]["age_years"]

    character = Character(
        user_id=user.id,
        display_name=DEMO_DISPLAY,
        home_state_id=state.id,
        current_state_id=state.id,
        home_state_locked=True,
        home_state_chosen_at=now - timedelta(days=120),
        age_years=age,
        cash=25000.0,
        bank_balance=75000.0,
        energy=100,
        max_energy=120,
        base_max_energy=100,
        reputation=55,
        heat=0.0,
        health=100,
        max_health=100,
        last_energy_at=now,
        last_heat_tick_at=now,
        last_health_at=now,
        last_bank_interest_at=now,
        bio="Demo mogul account — degrees, MBA, and Amir Consolidated Holdings.",
        is_homeless=False,
    )
    db.add(character)
    await db.flush()

    state.population_count += 1
    await housing_service.assign_starter_hostel(db, character)

    # Completed education
    for track, title in DEMO_DEGREES:
        meta = EDUCATION_CATALOG[track]
        started = now - timedelta(days=meta["real_days"] + 30)
        enrollment = EducationEnrollment(
            character_id=character.id,
            track=track,
            status=EnrollmentStatus.COMPLETED,
            title=title,
            cost_paid=meta["cost"],
            age_gain_years=meta["age_years"],
            education_level=meta["level"],
            started_at=started,
            completes_at=started + timedelta(days=meta["real_days"]),
            completed_at=started + timedelta(days=meta["real_days"]),
        )
        db.add(enrollment)

    # Big company
    business = Business(
        owner_id=character.id,
        state_id=state.id,
        name="Amir Consolidated Holdings",
        sector="other",
        entity_type="limited_company",
        description=(
            "National conglomerate: logistics, retail, and light manufacturing. "
            "Demo company with a large payroll."
        ),
        status=BusinessStatus.ACTIVE,
        cash_balance=150000.0,
        registered_at=now - timedelta(days=90),
        registration_completes_at=now - timedelta(days=90),
        local_address="100 Independence Avenue, Amirabad",
        is_home_state=True,
        is_public=False,
        last_ops_at=now,
        last_payroll_at=now,
    )
    db.add(business)
    await db.flush()

    staff = await employee_service.seed_staff(db, business.id, STAFF_ROSTER)
    await db.flush()

    return {
        "created": True,
        "username": DEMO_USERNAME,
        "password": DEMO_PASSWORD,
        "display_name": DEMO_DISPLAY,
        "character_id": character.id,
        "age_years": age,
        "degrees": len(DEMO_DEGREES),
        "business_id": business.id,
        "employees": staff,
        "cash": character.cash,
        "bank_balance": character.bank_balance,
    }
