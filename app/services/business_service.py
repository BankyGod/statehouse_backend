from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.business import Business, BusinessStatus
from app.models.character import Character
from app.models.permit import Permit, PermitStatus, PermitType
from app.models.state import State
from app.services.character_service import ensure_can_act

REGISTRATION_FEE = 150.0
REGISTRATION_HOURS = 12  # few hours to 1 day


async def register_business(
    db: AsyncSession,
    character: Character,
    *,
    name: str,
    sector: str,
    state_id: int,
    local_address: str,
    description: str | None,
) -> Business:
    ensure_can_act(character)

    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    is_home = state_id == character.home_state_id
    if not is_home:
        result = await db.execute(
            select(Permit).where(
                Permit.character_id == character.id,
                Permit.state_id == state_id,
                Permit.permit_type == PermitType.BUSINESS,
                Permit.status == PermitStatus.ACTIVE,
                Permit.expires_at > utcnow(),
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=403,
                detail="Business permit required to register outside home state",
            )

    if character.cash < REGISTRATION_FEE:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    now = utcnow()
    completes = now + timedelta(hours=REGISTRATION_HOURS)
    character.cash -= REGISTRATION_FEE

    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.BUSINESS,
        status=ActivityStatus.IN_PROGRESS,
        title=f"Registering {name}",
        age_gain_years=0,
        cash_delta=-REGISTRATION_FEE,
        started_at=now,
        completes_at=completes,
    )
    db.add(activity)
    await db.flush()
    from app.services.notify_service import broadcast_activity, broadcast_character

    await broadcast_activity(activity)
    await broadcast_character(character)

    business = Business(
        owner_id=character.id,
        state_id=state_id,
        name=name,
        sector=sector,
        description=description,
        status=BusinessStatus.PENDING,
        cash_balance=0,
        registration_completes_at=completes,
        local_address=local_address,
        is_home_state=is_home,
    )
    db.add(business)
    await db.flush()
    await db.refresh(business)
    return business


async def activate_due_businesses(
    db: AsyncSession, character: Character
) -> list[Business]:
    now = utcnow()
    result = await db.execute(
        select(Business).where(
            Business.owner_id == character.id,
            Business.status == BusinessStatus.PENDING,
            Business.registration_completes_at <= now,
        )
    )
    activated = []
    for biz in result.scalars().all():
        biz.status = BusinessStatus.ACTIVE
        biz.registered_at = now
        biz.last_ops_at = now
        biz.last_payroll_at = now
        activated.append(biz)
        from app.services import notify_service

        await notify_service.push(
            db,
            character.id,
            f"{biz.name} is now active",
            body="Your company can hire staff and earn revenue.",
            category="business",
            ref_type="business",
            ref_id=biz.id,
        )
    if activated:
        await db.flush()
    return activated


ROLE_REVENUE = {
    "labourer": 22.0,
    "clerk": 35.0,
    "specialist": 55.0,
    "manager": 80.0,
    "executive": 110.0,
}


async def deposit(
    db: AsyncSession, character: Character, business_id: int, amount: float
) -> dict:
    ensure_can_act(character)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if character.cash < amount:
        raise HTTPException(status_code=400, detail="Insufficient cash")
    character.cash = round(character.cash - amount, 2)
    business.cash_balance = round(business.cash_balance + amount, 2)
    await db.flush()
    return {
        "business_id": business.id,
        "deposited": amount,
        "business_cash": business.cash_balance,
        "cash": character.cash,
    }


async def withdraw(
    db: AsyncSession, character: Character, business_id: int, amount: float
) -> dict:
    ensure_can_act(character)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.is_public:
        raise HTTPException(
            status_code=400,
            detail="Public companies cannot withdraw cash to the owner",
        )
    if business.cash_balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient business cash")
    business.cash_balance = round(business.cash_balance - amount, 2)
    character.cash = round(character.cash + amount, 2)
    await db.flush()
    return {
        "business_id": business.id,
        "withdrawn": amount,
        "business_cash": business.cash_balance,
        "cash": character.cash,
    }


def _employee_revenue(employees) -> float:
    total = 0.0
    for emp in employees:
        role = emp.role.value if hasattr(emp.role, "value") else str(emp.role)
        total += ROLE_REVENUE.get(role.lower(), 20.0)
    return total


async def process_business_ops(db: AsyncSession, character: Character) -> dict:
    """Accrue revenue on interval; pay weekly wages from company cash."""
    from app.core.config import get_settings
    from app.models.employee import BusinessEmployee
    from app.services import notify_service

    settings = get_settings()
    now = utcnow()
    result = await db.execute(
        select(Business).where(
            Business.owner_id == character.id,
            Business.status == BusinessStatus.ACTIVE,
        )
    )
    summary = {"revenue": 0.0, "wages": 0.0, "businesses": 0}

    for biz in result.scalars().all():
        summary["businesses"] += 1
        emps_result = await db.execute(
            select(BusinessEmployee).where(
                BusinessEmployee.business_id == biz.id,
                BusinessEmployee.is_active.is_(True),
            )
        )
        employees = list(emps_result.scalars().all())

        last_ops = biz.last_ops_at or biz.registered_at or now
        if last_ops.tzinfo is None:
            from datetime import timezone

            last_ops = last_ops.replace(tzinfo=timezone.utc)
        hours = (now - last_ops).total_seconds() / 3600.0
        interval = settings.business_ops_interval_hours
        if hours >= interval:
            ticks = int(hours // interval)
            staff_rev = _employee_revenue(employees)
            earned = round(
                ticks
                * (settings.business_base_revenue_per_interval + staff_rev),
                2,
            )
            biz.cash_balance = round(biz.cash_balance + earned, 2)
            biz.lifetime_revenue = round(biz.lifetime_revenue + earned, 2)
            biz.last_ops_at = last_ops + timedelta(hours=ticks * interval)
            summary["revenue"] += earned
            if earned > 0:
                await notify_service.push(
                    db,
                    character.id,
                    f"{biz.name} earned ${earned:.2f}",
                    body=f"Company cash ${biz.cash_balance:.2f}",
                    category="business",
                    ref_type="business",
                    ref_id=biz.id,
                )

        last_pay = biz.last_payroll_at or biz.registered_at or now
        if last_pay.tzinfo is None:
            from datetime import timezone

            last_pay = last_pay.replace(tzinfo=timezone.utc)
        days = (now - last_pay).total_seconds() / 86400.0
        if days >= settings.business_payroll_days and employees:
            wage_bill = round(sum(e.wage_per_week for e in employees), 2)
            paid = min(wage_bill, biz.cash_balance)
            biz.cash_balance = round(biz.cash_balance - paid, 2)
            biz.lifetime_wages = round(biz.lifetime_wages + paid, 2)
            biz.last_payroll_at = now
            summary["wages"] += paid

            # Pay player employees their share
            if paid > 0 and wage_bill > 0:
                ratio = paid / wage_bill
                for emp in employees:
                    if emp.character_id and emp.is_active:
                        worker = await db.get(Character, emp.character_id)
                        if worker:
                            cut = round(emp.wage_per_week * ratio, 2)
                            worker.cash = round(worker.cash + cut, 2)
                            await notify_service.push(
                                db,
                                worker.id,
                                f"Payday from {biz.name}",
                                body=f"+${cut:.2f}",
                                category="job",
                            )
            await notify_service.push(
                db,
                character.id,
                f"{biz.name} payroll ${paid:.2f}",
                body=(
                    "Fully paid"
                    if paid >= wage_bill
                    else f"Shortfall — owed ${wage_bill - paid:.2f}"
                ),
                category="business",
            )

    await db.flush()
    return summary
