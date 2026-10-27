from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.business import Business, BusinessStatus
from app.models.character import Character
from app.models.employee import (
    BusinessEmployee,
    EmployeeRole,
    JobInvite,
    JobInviteStatus,
)
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


def _invite_out(invite: JobInvite, *, business_name: str, from_name: str, to_name: str) -> dict:
    return {
        "id": invite.id,
        "business_id": invite.business_id,
        "business_name": business_name,
        "from_character_id": invite.from_character_id,
        "from_display_name": from_name,
        "to_character_id": invite.to_character_id,
        "to_display_name": to_name,
        "role": invite.role.value if hasattr(invite.role, "value") else str(invite.role),
        "wage_per_week": invite.wage_per_week,
        "message": invite.message,
        "status": invite.status.value if hasattr(invite.status, "value") else str(invite.status),
        "posted_at": invite.posted_at,
        "responded_at": invite.responded_at,
    }


async def hire_player(
    db: AsyncSession,
    owner: Character,
    business_id: int,
    *,
    display_name: str | None = None,
    character_id: int | None = None,
    role: EmployeeRole = EmployeeRole.CLERK,
    wage_per_week: float | None = None,
    message: str | None = None,
) -> dict:
    """Send a job invitation — worker must accept before joining payroll."""
    from sqlalchemy import func

    from app.services import notify_service, social_service

    ensure_can_act(owner)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business must be active")

    worker: Character | None = None
    if character_id is not None:
        worker = await db.get(Character, int(character_id))
    elif display_name:
        name = display_name.strip()
        result = await db.execute(
            select(Character).where(
                func.lower(Character.display_name) == name.lower()
            )
        )
        worker = result.scalar_one_or_none()
    else:
        raise HTTPException(
            status_code=400, detail="Provide character_id or display_name"
        )

    if worker is None or getattr(worker, "is_npc", False):
        raise HTTPException(status_code=404, detail="Player not found")
    if worker.id == owner.id:
        raise HTTPException(status_code=400, detail="Cannot hire yourself")

    from app.services import office_pay_service

    if await office_pay_service.holds_political_office(db, worker):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{worker.display_name} holds political office and cannot join "
                "a company as an employee (they may still own a business)."
            ),
        )

    existing = await db.execute(
        select(BusinessEmployee).where(
            BusinessEmployee.character_id == worker.id,
            BusinessEmployee.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Player already employed")

    pending = await db.execute(
        select(JobInvite).where(
            JobInvite.business_id == business.id,
            JobInvite.to_character_id == worker.id,
            JobInvite.status == JobInviteStatus.PENDING,
        )
    )
    if pending.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="A pending invite already exists for this player"
        )

    wage = wage_per_week if wage_per_week and wage_per_week > 0 else ROLE_WAGES[role]
    if business.cash_balance < wage:
        raise HTTPException(
            status_code=400,
            detail=f"Business needs ${wage:.0f} cash reserved for the first week",
        )

    note = (message or "").strip()[:500] or None
    invite = JobInvite(
        business_id=business.id,
        from_character_id=owner.id,
        to_character_id=worker.id,
        role=role,
        wage_per_week=wage,
        message=note,
        status=JobInviteStatus.PENDING,
        posted_at=utcnow(),
    )
    db.add(invite)
    await db.flush()

    mail_body = (
        f"{business.name} offered you a {role.value} role at ${wage:.0f}/week."
        + (f"\n\n{note}" if note else "")
        + "\n\nOpen Inbox → Job offers to accept or decline."
    )
    await social_service.send_mail(
        db,
        owner,
        to_character_id=worker.id,
        body=mail_body,
        subject=f"Job offer — {business.name}",
        business_id=business.id,
    )
    await notify_service.push(
        db,
        worker.id,
        f"Job offer from {business.name}",
        body=f"{role.value} · ${wage:.0f}/wk — check Inbox to respond",
        category="job",
        ref_type="job_invite",
        ref_id=invite.id,
    )
    await db.refresh(invite)
    return _invite_out(
        invite,
        business_name=business.name,
        from_name=owner.display_name,
        to_name=worker.display_name,
    )


async def list_incoming_invites(db: AsyncSession, character: Character) -> list[dict]:
    result = await db.execute(
        select(JobInvite)
        .where(
            JobInvite.to_character_id == character.id,
            JobInvite.status == JobInviteStatus.PENDING,
        )
        .order_by(JobInvite.id.desc())
    )
    out = []
    for inv in result.scalars().all():
        biz = await db.get(Business, inv.business_id)
        fr = await db.get(Character, inv.from_character_id)
        to = await db.get(Character, inv.to_character_id)
        out.append(
            _invite_out(
                inv,
                business_name=biz.name if biz else f"#{inv.business_id}",
                from_name=fr.display_name if fr else "?",
                to_name=to.display_name if to else "?",
            )
        )
    return out


async def list_outgoing_invites(
    db: AsyncSession, owner: Character, business_id: int
) -> list[dict]:
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(JobInvite)
        .where(
            JobInvite.business_id == business_id,
            JobInvite.status == JobInviteStatus.PENDING,
        )
        .order_by(JobInvite.id.desc())
    )
    out = []
    for inv in result.scalars().all():
        fr = await db.get(Character, inv.from_character_id)
        to = await db.get(Character, inv.to_character_id)
        out.append(
            _invite_out(
                inv,
                business_name=business.name,
                from_name=fr.display_name if fr else "?",
                to_name=to.display_name if to else "?",
            )
        )
    return out


async def accept_invite(db: AsyncSession, character: Character, invite_id: int) -> dict:
    from app.services import job_service, notify_service, office_pay_service, social_service

    ensure_can_act(character)
    invite = await db.get(JobInvite, invite_id)
    if invite is None or invite.to_character_id != character.id:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != JobInviteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invite is no longer pending")

    if await office_pay_service.holds_political_office(db, character):
        raise HTTPException(
            status_code=400,
            detail=office_pay_service.EMPLOYEE_JOB_BLOCKED_BY_OFFICE,
        )

    business = await db.get(Business, invite.business_id)
    if business is None or business.status != BusinessStatus.ACTIVE:
        invite.status = JobInviteStatus.CANCELLED
        invite.responded_at = utcnow()
        await db.flush()
        raise HTTPException(status_code=400, detail="Company is no longer active")

    wage = float(invite.wage_per_week)
    if business.cash_balance < wage:
        raise HTTPException(
            status_code=400,
            detail="Company cannot cover the first week’s wage right now — try again later",
        )

    # Leave previous work automatically (state job + any other company role)
    left_state_job = await job_service.resign_current_job(db, character)
    left_company = None
    prior = await db.execute(
        select(BusinessEmployee).where(
            BusinessEmployee.character_id == character.id,
            BusinessEmployee.is_active.is_(True),
        )
    )
    for old in prior.scalars().all():
        if old.business_id == business.id:
            continue
        old.is_active = False
        left_company = old.business_id
        old_biz = await db.get(Business, old.business_id)
        if old_biz:
            await notify_service.push(
                db,
                old_biz.owner_id,
                f"{character.display_name} left {old_biz.name}",
                body="Accepted another company job offer",
                category="job",
            )

    business.cash_balance = round(business.cash_balance - wage, 2)
    emp = BusinessEmployee(
        business_id=business.id,
        character_id=character.id,
        display_name=character.display_name,
        role=invite.role,
        wage_per_week=wage,
        is_npc=False,
        is_active=True,
        hired_at=utcnow(),
    )
    db.add(emp)
    invite.status = JobInviteStatus.ACCEPTED
    invite.responded_at = utcnow()
    await db.flush()

    await notify_service.push(
        db,
        invite.from_character_id,
        f"{character.display_name} joined {business.name}",
        body=f"Accepted {invite.role.value} at ${wage:.0f}/wk",
        category="job",
        ref_type="job_invite",
        ref_id=invite.id,
    )
    await social_service.send_mail(
        db,
        character,
        to_character_id=invite.from_character_id,
        body=f"I accepted the {invite.role.value} offer at {business.name} (${wage:.0f}/wk).",
        subject=f"Accepted — {business.name}",
        business_id=None,
    )
    await db.refresh(emp)
    note_bits = [f"You joined {business.name}"]
    if left_state_job:
        note_bits.append("previous state job ended")
    if left_company:
        note_bits.append("previous company job ended")
    return {
        "invite_id": invite.id,
        "employee_id": emp.id,
        "business_id": business.id,
        "business_name": business.name,
        "role": emp.role.value if hasattr(emp.role, "value") else str(emp.role),
        "wage_per_week": emp.wage_per_week,
        "left_state_job": left_state_job,
        "left_company_job": left_company is not None,
        "message": " — ".join(note_bits),
    }


async def decline_invite(db: AsyncSession, character: Character, invite_id: int) -> dict:
    from app.services import notify_service, social_service

    ensure_can_act(character)
    invite = await db.get(JobInvite, invite_id)
    if invite is None or invite.to_character_id != character.id:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != JobInviteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invite is no longer pending")

    invite.status = JobInviteStatus.DECLINED
    invite.responded_at = utcnow()
    business = await db.get(Business, invite.business_id)
    await notify_service.push(
        db,
        invite.from_character_id,
        f"{character.display_name} declined your offer",
        body=business.name if business else "Job invite declined",
        category="job",
        ref_type="job_invite",
        ref_id=invite.id,
    )
    await social_service.send_mail(
        db,
        character,
        to_character_id=invite.from_character_id,
        body=f"I declined the job offer"
        + (f" from {business.name}." if business else "."),
        subject="Job offer declined",
    )
    await db.flush()
    return {"invite_id": invite.id, "status": "declined"}


async def cancel_invite(
    db: AsyncSession, owner: Character, business_id: int, invite_id: int
) -> dict:
    ensure_can_act(owner)
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Business not found")
    invite = await db.get(JobInvite, invite_id)
    if (
        invite is None
        or invite.business_id != business_id
        or invite.status != JobInviteStatus.PENDING
    ):
        raise HTTPException(status_code=404, detail="Pending invite not found")
    invite.status = JobInviteStatus.CANCELLED
    invite.responded_at = utcnow()
    await db.flush()
    return {"invite_id": invite.id, "status": "cancelled"}


async def my_company_job(db: AsyncSession, character: Character) -> dict | None:
    from app.services import office_pay_service

    if await office_pay_service.holds_political_office(db, character):
        await office_pay_service.end_employee_jobs_for_office(
            db, character, reason="Holds political office"
        )
        return None

    result = await db.execute(
        select(BusinessEmployee).where(
            BusinessEmployee.character_id == character.id,
            BusinessEmployee.is_active.is_(True),
            BusinessEmployee.is_npc.is_(False),
        )
    )
    emp = result.scalar_one_or_none()
    if emp is None:
        return None
    business = await db.get(Business, emp.business_id)
    return {
        "employee_id": emp.id,
        "business_id": emp.business_id,
        "business_name": business.name if business else f"#{emp.business_id}",
        "role": emp.role.value if hasattr(emp.role, "value") else str(emp.role),
        "wage_per_week": emp.wage_per_week,
        "hired_at": emp.hired_at,
        "display_name": emp.display_name,
    }


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
