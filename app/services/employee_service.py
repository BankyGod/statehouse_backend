from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.business import Business, BusinessStatus
from app.models.character import Character
from app.models.employee import BusinessEmployee, EmployeeRole
from app.services.character_service import ensure_can_act

NPC_NAME_POOL = [
    "Kwesi Mensah",
    "Ama Boateng",
    "Ibrahim Sule",
    "Efua Darko",
    "Yaw Owusu",
    "Nadia Traore",
    "Kofi Adjei",
    "Grace Addo",
    "Samuel Tetteh",
    "Priya Nkrumah",
    "Daniel Okoro",
    "Helen Quaye",
    "Omar Diallo",
    "Ruth Asante",
    "Marcus Hale",
    "Fatima Rahman",
    "Leroy Banks",
    "Claire Mensah",
    "Ethan Cole",
    "Victoria Okeke",
    "Joseph Addai",
    "Elena Frost",
    "Amina Diallo",
    "Bankole Sarpong",
]

ROLE_WAGES = {
    EmployeeRole.LABOURER: 70.0,
    EmployeeRole.CLERK: 95.0,
    EmployeeRole.SPECIALIST: 140.0,
    EmployeeRole.MANAGER: 220.0,
    EmployeeRole.EXECUTIVE: 350.0,
}


async def list_employees(db: AsyncSession, business_id: int) -> list[BusinessEmployee]:
    result = await db.execute(
        select(BusinessEmployee).where(
            BusinessEmployee.business_id == business_id,
            BusinessEmployee.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def employee_count(db: AsyncSession, business_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(BusinessEmployee)
        .where(
            BusinessEmployee.business_id == business_id,
            BusinessEmployee.is_active.is_(True),
        )
    )
    return int(result.scalar_one())


async def hire_npc(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    role: EmployeeRole = EmployeeRole.LABOURER,
    display_name: str | None = None,
) -> BusinessEmployee:
    ensure_can_act(character)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business must be active")

    wage = ROLE_WAGES[role]
    # Hiring fee = 1 week wage from business cash
    if business.cash_balance < wage:
        raise HTTPException(
            status_code=400,
            detail=f"Business needs ${wage:.0f} cash to hire ({role.value})",
        )

    count = await employee_count(db, business_id)
    name = display_name or NPC_NAME_POOL[count % len(NPC_NAME_POOL)]
    # Avoid exact dup names in same company
    name = f"{name}" if count < len(NPC_NAME_POOL) else f"{name} {count + 1}"

    business.cash_balance = round(business.cash_balance - wage, 2)
    emp = BusinessEmployee(
        business_id=business.id,
        character_id=None,
        display_name=name,
        role=role,
        wage_per_week=wage,
        is_npc=True,
        is_active=True,
        hired_at=utcnow(),
    )
    db.add(emp)
    await db.flush()
    await db.refresh(emp)
    return emp


async def hire_player(
    db: AsyncSession,
    owner: Character,
    business_id: int,
    *,
    display_name: str,
    role: EmployeeRole = EmployeeRole.CLERK,
    wage_per_week: float | None = None,
) -> BusinessEmployee:
    """Hire another player character onto the company payroll."""
    ensure_can_act(owner)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business must be active")

    result = await db.execute(
        select(Character).where(Character.display_name == display_name)
    )
    worker = result.scalar_one_or_none()
    if worker is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if worker.id == owner.id:
        raise HTTPException(status_code=400, detail="Cannot hire yourself")

    existing = await db.execute(
        select(BusinessEmployee).where(
            BusinessEmployee.character_id == worker.id,
            BusinessEmployee.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Player already employed")

    wage = wage_per_week if wage_per_week and wage_per_week > 0 else ROLE_WAGES[role]
    if business.cash_balance < wage:
        raise HTTPException(
            status_code=400,
            detail=f"Business needs ${wage:.0f} cash to hire",
        )
    business.cash_balance = round(business.cash_balance - wage, 2)
    emp = BusinessEmployee(
        business_id=business.id,
        character_id=worker.id,
        display_name=worker.display_name,
        role=role,
        wage_per_week=wage,
        is_npc=False,
        is_active=True,
        hired_at=utcnow(),
    )
    db.add(emp)
    from app.services import notify_service

    await notify_service.push(
        db,
        worker.id,
        f"Hired by {business.name}",
        body=f"Role {role.value}, ${wage:.0f}/week",
        category="job",
    )
    await db.flush()
    await db.refresh(emp)
    return emp


async def fire_employee(
    db: AsyncSession, character: Character, business_id: int, employee_id: int
) -> dict:
    ensure_can_act(character)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    emp = await db.get(BusinessEmployee, employee_id)
    if emp is None or emp.business_id != business_id or not emp.is_active:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.is_active = False
    await db.flush()
    return {"id": emp.id, "message": f"{emp.display_name} was let go"}


async def update_employee(
    db: AsyncSession,
    character: Character,
    business_id: int,
    employee_id: int,
    *,
    role: EmployeeRole | None = None,
    wage_per_week: float | None = None,
    display_name: str | None = None,
) -> BusinessEmployee:
    """Owner can change role, weekly wage, or display name for active staff."""
    ensure_can_act(character)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business is not active yet")
    emp = await db.get(BusinessEmployee, employee_id)
    if emp is None or emp.business_id != business_id or not emp.is_active:
        raise HTTPException(status_code=404, detail="Employee not found")

    if role is not None:
        emp.role = role
        # Default wage to role band if wage not also provided
        if wage_per_week is None:
            emp.wage_per_week = ROLE_WAGES[role]
    if wage_per_week is not None:
        wage = round(float(wage_per_week), 2)
        if wage <= 0:
            raise HTTPException(status_code=400, detail="Wage must be positive")
        emp.wage_per_week = wage
    if display_name is not None:
        name = display_name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="Display name too short")
        emp.display_name = name[:64]

    await db.flush()
    await db.refresh(emp)
    return emp


async def seed_staff(
    db: AsyncSession, business_id: int, roster: list[tuple[str, EmployeeRole]]
) -> int:
    now = utcnow()
    created = 0
    for name, role in roster:
        db.add(
            BusinessEmployee(
                business_id=business_id,
                character_id=None,
                display_name=name,
                role=role,
                wage_per_week=ROLE_WAGES[role],
                is_npc=True,
                is_active=True,
                hired_at=now,
            )
        )
        created += 1
    await db.flush()
    return created
