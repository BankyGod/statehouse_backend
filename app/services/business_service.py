from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.activity import Activity, ActivityStatus, ActivityType
from app.models.business import (
    ENTITY_TYPE_CATALOG,
    SECTOR_CATALOG,
    Business,
    BusinessEntityType,
    BusinessSector,
    BusinessStatus,
)
from app.models.character import Character
from app.models.permit import Permit, PermitStatus, PermitType
from app.models.state import State
from app.services.character_service import ensure_can_act

REGISTRATION_HOURS = 12  # few hours to 1 day
DEFAULT_REGISTRATION_FEE = 150.0


def _fee_for_entity(entity_type: BusinessEntityType) -> float:
    for row in ENTITY_TYPE_CATALOG:
        if row["value"] == entity_type:
            return float(row["registration_fee"])
    return DEFAULT_REGISTRATION_FEE


def registration_catalog() -> dict:
    return {
        "sectors": [
            {
                "value": row["value"].value,
                "label": row["label"],
                "group": row["group"],
            }
            for row in SECTOR_CATALOG
        ],
        "entity_types": [
            {
                "value": row["value"].value,
                "label": row["label"],
                "registration_fee": row["registration_fee"],
                "blurb": row["blurb"],
            }
            for row in ENTITY_TYPE_CATALOG
        ],
        "registration_hours": REGISTRATION_HOURS,
        "min_starting_capital": 0.0,
        "max_starting_capital": 50000.0,
    }


async def has_business_permit(
    db: AsyncSession, character: Character, state_id: int
) -> bool:
    if state_id == character.home_state_id:
        return True
    result = await db.execute(
        select(Permit).where(
            Permit.character_id == character.id,
            Permit.state_id == state_id,
            Permit.permit_type == PermitType.BUSINESS,
            Permit.status == PermitStatus.ACTIVE,
            Permit.expires_at > utcnow(),
        )
    )
    return result.scalar_one_or_none() is not None


async def registration_preview(
    db: AsyncSession,
    character: Character,
    *,
    state_id: int,
    entity_type: BusinessEntityType,
    starting_capital: float = 0.0,
) -> dict:
    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")
    fee = _fee_for_entity(entity_type)
    capital = max(0.0, round(float(starting_capital or 0), 2))
    is_home = state_id == character.home_state_id
    permit_ok = await has_business_permit(db, character, state_id)
    total = round(fee + capital, 2)
    return {
        "state_id": state_id,
        "state_name": state.name,
        "is_home_state": is_home,
        "permit_required": not is_home,
        "permit_ok": permit_ok,
        "entity_type": entity_type.value,
        "registration_fee": fee,
        "starting_capital": capital,
        "total_due": total,
        "registration_hours": REGISTRATION_HOURS,
        "cash_on_hand": round(character.cash, 2),
        "can_afford": character.cash >= total,
    }


async def register_business(
    db: AsyncSession,
    character: Character,
    *,
    name: str,
    sector: str,
    state_id: int,
    local_address: str,
    description: str | None,
    entity_type: str = BusinessEntityType.SOLE_TRADER.value,
    starting_capital: float = 0.0,
) -> Business:
    ensure_can_act(character)

    try:
        sector_enum = BusinessSector(sector)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid sector — choose from the business catalog",
        ) from exc

    try:
        entity_enum = BusinessEntityType(entity_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid business type") from exc

    capital = round(float(starting_capital or 0), 2)
    if capital < 0:
        raise HTTPException(status_code=400, detail="Starting capital cannot be negative")
    if capital > 50000:
        raise HTTPException(status_code=400, detail="Starting capital max is 50000")

    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    is_home = state_id == character.home_state_id
    if not is_home and not await has_business_permit(db, character, state_id):
        raise HTTPException(
            status_code=403,
            detail="Business permit required to register outside home state",
        )

    fee = _fee_for_entity(entity_enum)
    total = round(fee + capital, 2)
    if character.cash < total:
        raise HTTPException(
            status_code=400,
            detail=f"Need {total:.2f} cash (fee {fee:.2f} + capital {capital:.2f})",
        )

    now = utcnow()
    completes = now + timedelta(hours=REGISTRATION_HOURS)
    character.cash -= total
    if fee > 0:
        from app.services import treasury_service

        await treasury_service.collect_fee(
            db,
            fee,
            note=f"Business registration — {name}",
            character_id=character.id,
        )

    activity = Activity(
        character_id=character.id,
        activity_type=ActivityType.BUSINESS,
        status=ActivityStatus.IN_PROGRESS,
        title=f"Registering {name}",
        description=f"{entity_enum.value.replace('_', ' ')} · {sector_enum.value}",
        age_gain_years=0,
        cash_delta=-total,
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
        sector=sector_enum.value,
        entity_type=entity_enum.value,
        description=description,
        status=BusinessStatus.PENDING,
        cash_balance=capital,
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
    from app.services import treasury_service

    # Owner draw is taxable personal income
    pay = await treasury_service.pay_taxable_income(
        db,
        character,
        amount,
        note=f"Income tax — draw from {business.name}",
    )
    await db.flush()
    return {
        "business_id": business.id,
        "withdrawn": amount,
        "gross": pay["gross"],
        "tax": pay["tax"],
        "net": pay["net"],
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
    from app.services import performance_service

    for biz in result.scalars().all():
        summary["businesses"] += 1
        emps_result = await db.execute(
            select(BusinessEmployee).where(
                BusinessEmployee.business_id == biz.id,
                BusinessEmployee.is_active.is_(True),
            )
        )
        employees = list(emps_result.scalars().all())
        interval_rev = 0.0
        interval_wages = 0.0

        last_ops = biz.last_ops_at or biz.registered_at or now
        if last_ops.tzinfo is None:
            from datetime import timezone

            last_ops = last_ops.replace(tzinfo=timezone.utc)
        hours = (now - last_ops).total_seconds() / 3600.0
        interval = settings.business_ops_interval_hours
        if hours >= interval:
            ticks = int(hours // interval)
            sector = biz.sector.value if hasattr(biz.sector, "value") else str(biz.sector)
            from app.seed.sector_catalog import sector_mode

            staff_rev = _employee_revenue(employees)
            mode = sector_mode(sector)
            # Real money comes from player commerce / housing — not formula minting.
            # Ops only add thin staff activity (management) for listed sectors.
            if sector == BusinessSector.REAL_ESTATE.value:
                earned = round(ticks * (staff_rev * 0.35), 2)
            elif mode in ("inventory", "services", "mixed"):
                # Staff keep the lights on; sales/bookings credit cash on commerce events
                earned = round(ticks * (staff_rev * 0.15), 2)
            else:
                earned = round(
                    ticks
                    * (settings.business_base_revenue_per_interval * 0.35 + staff_rev * 0.5),
                    2,
                )
            from app.services import treasury_service

            tax_split = await treasury_service.take_corporate_tax(
                db,
                earned,
                business_id=biz.id,
                note=f"Corporate tax — {biz.name}",
            )
            net_earned = tax_split["net"]
            biz.cash_balance = round(biz.cash_balance + net_earned, 2)
            biz.lifetime_revenue = round(biz.lifetime_revenue + net_earned, 2)
            biz.last_ops_at = last_ops + timedelta(hours=ticks * interval)
            summary["revenue"] += net_earned
            interval_rev += net_earned
            if earned > 0:
                tax_note = (
                    f" · tax ${tax_split['tax']:.2f}"
                    if tax_split["tax"] > 0
                    else ""
                )
                label = (
                    "management fees"
                    if sector == BusinessSector.REAL_ESTATE.value
                    or mode in ("inventory", "services", "mixed")
                    else "earned"
                )
                await notify_service.push(
                    db,
                    character.id,
                    f"{biz.name} {label} ${net_earned:.2f}",
                    body=f"Company cash ${biz.cash_balance:.2f}{tax_note}",
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
            interval_wages += paid

            # Pay player employees their share (income tax withheld → treasury)
            if paid > 0 and wage_bill > 0:
                from app.services import treasury_service

                ratio = paid / wage_bill
                for emp in employees:
                    if emp.character_id and emp.is_active:
                        worker = await db.get(Character, emp.character_id)
                        if worker:
                            cut = round(emp.wage_per_week * ratio, 2)
                            pay = await treasury_service.pay_taxable_income(
                                db,
                                worker,
                                cut,
                                note=f"Income tax — payroll {biz.name}",
                            )
                            await notify_service.push(
                                db,
                                worker.id,
                                f"Payday from {biz.name}",
                                body=(
                                    f"+${pay['net']:.2f}"
                                    + (
                                        f" (tax ${pay['tax']:.2f})"
                                        if pay["tax"] > 0
                                        else ""
                                    )
                                ),
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

        if interval_rev > 0 or interval_wages > 0:
            await performance_service.record_snapshot(
                db,
                biz,
                interval_revenue=interval_rev,
                interval_wages=interval_wages,
            )
            await performance_service.apply_ops_to_stock_price(
                db,
                biz,
                interval_revenue=interval_rev,
                interval_wages=interval_wages,
            )

    await db.flush()
    return summary


async def process_all_active_business_ops(db: AsyncSession) -> dict:
    """World-tick ops for every active business (not only logged-in owners)."""
    result = await db.execute(
        select(Business.owner_id)
        .where(Business.status == BusinessStatus.ACTIVE)
        .distinct()
    )
    owners = [oid for (oid,) in result.all() if oid]
    total = {"revenue": 0.0, "wages": 0.0, "owners": 0}
    for oid in owners:
        ch = await db.get(Character, oid)
        if ch is None:
            continue
        summary = await process_business_ops(db, ch)
        total["revenue"] += float(summary.get("revenue") or 0)
        total["wages"] += float(summary.get("wages") or 0)
        total["owners"] += 1
    return total
