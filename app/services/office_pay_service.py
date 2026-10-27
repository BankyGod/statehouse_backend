"""Salaries, allowances, and bonuses for President / VP / Speaker / Ministers / MPs."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.cabinet import CabinetSeat, Portfolio
from app.models.character import Character
from app.models.legislation import BillVoteChoice, BudgetVote
from app.models.state import State
from app.models.treasury import TreasuryTxType


def _aware(dt):
    if dt is not None and getattr(dt, "tzinfo", None) is None:
        from datetime import timezone

        return dt.replace(tzinfo=timezone.utc)
    return dt


def office_pay_catalog() -> dict:
    s = get_settings()
    offices = {
        "president": {
            "label": "President",
            "salary": s.president_weekly_salary,
            "duty_allowance": s.president_duty_allowance,
            "housing_allowance": s.president_housing_allowance,
        },
        "vice_president": {
            "label": "Vice President",
            "salary": s.vp_weekly_salary,
            "duty_allowance": s.vp_duty_allowance,
            "housing_allowance": s.vp_housing_allowance,
        },
        "speaker": {
            "label": "Speaker",
            "salary": s.speaker_weekly_salary,
            "duty_allowance": s.speaker_duty_allowance,
            "housing_allowance": s.speaker_housing_allowance,
        },
        "minister": {
            "label": "Minister",
            "salary": s.minister_weekly_salary,
            "duty_allowance": s.minister_duty_allowance,
            "housing_allowance": s.minister_housing_allowance,
        },
        "mp": {
            "label": "Member of Parliament",
            "salary": s.mp_weekly_salary,
            "duty_allowance": s.mp_duty_allowance,
            "housing_allowance": s.mp_housing_allowance,
        },
    }
    for row in offices.values():
        row["weekly_total"] = round(
            float(row["salary"])
            + float(row["duty_allowance"])
            + float(row["housing_allowance"]),
            2,
        )
    return {
        "offices": offices,
        "bonuses": {
            "session_mp": s.office_session_bonus_mp,
            "session_minister": s.office_session_bonus_minister,
            "budget_president": s.office_budget_bonus_president,
            "budget_finance": s.office_budget_bonus_finance,
            "budget_mp_yes": s.office_budget_bonus_mp_yes,
            "election_president": s.office_election_bonus_president,
            "election_mp": s.office_election_bonus_mp,
        },
        "scandal": {
            "heat_threshold": s.office_scandal_heat_threshold,
            "pay_factor": s.office_scandal_pay_factor,
        },
        "note": "Weekly pay from national treasury (taxed as income). NPCs are not paid.",
    }


def package_for(office_key: str) -> dict:
    return office_pay_catalog()["offices"][office_key]


def scandal_applies(character: Character) -> bool:
    s = get_settings()
    if float(character.heat or 0) >= s.office_scandal_heat_threshold:
        return True
    return bool(character.criminal_record_summary)


def weekly_gross(office_key: str, character: Character) -> dict:
    pkg = package_for(office_key)
    base = float(pkg["weekly_total"])
    scandal = scandal_applies(character)
    factor = get_settings().office_scandal_pay_factor if scandal else 1.0
    gross = round(base * factor, 2)
    return {
        "office": office_key,
        "salary": pkg["salary"],
        "duty_allowance": pkg["duty_allowance"],
        "housing_allowance": pkg["housing_allowance"],
        "weekly_total": pkg["weekly_total"],
        "scandal": scandal,
        "gross": gross,
    }


async def _pay_character(
    db: AsyncSession,
    character: Character,
    amount: float,
    *,
    note: str,
) -> float:
    if amount <= 0:
        return 0.0
    from app.services import notify_service, treasury_service

    funded = await treasury_service.debit(
        db,
        amount,
        TreasuryTxType.SALARY,
        note=note,
        character_id=character.id,
        allow_overdraft=True,
    )
    if funded <= 0:
        return 0.0
    await treasury_service.pay_taxable_income(
        db,
        character,
        funded,
        note=f"Income tax — {note}",
    )
    await notify_service.push(
        db,
        character.id,
        "Office pay",
        body=f"{note}: ${funded:.2f} (before tax)",
        category="politics",
    )
    return funded


def _due(last, now) -> bool:
    last = _aware(last)
    if last is None:
        return True
    return now >= last + timedelta(days=7)


async def pay_all_office_salaries(db: AsyncSession) -> dict:
    """Weekly payroll for player President, VP, Speaker, Ministers, MPs."""
    from app.services import politics_service

    now = utcnow()
    nation = await politics_service.get_or_create_nation(db)
    paid = {
        "president": 0.0,
        "vice_president": 0.0,
        "speaker": 0.0,
        "ministers": 0.0,
        "mps": 0.0,
        "count": 0,
    }

    async def pay_office(
        character_id: int | None,
        office_key: str,
        last_attr: str,
        label: str,
    ) -> None:
        if not character_id:
            return
        if not _due(getattr(nation, last_attr, None), now):
            return
        ch = await db.get(Character, character_id)
        if ch is None:
            return
        info = weekly_gross(office_key, ch)
        funded = await _pay_character(
            db,
            ch,
            info["gross"],
            note=f"{label} weekly pay"
            + (" (scandal cut)" if info["scandal"] else ""),
        )
        setattr(nation, last_attr, now)
        paid[office_key if office_key != "minister" else "ministers"] = (
            paid.get(office_key if office_key != "minister" else "ministers", 0)
            + funded
        )
        if funded:
            paid["count"] += 1

    await pay_office(
        nation.president_character_id,
        "president",
        "last_president_salary_at",
        "President",
    )
    await pay_office(
        getattr(nation, "vice_president_character_id", None),
        "vice_president",
        "last_vp_salary_at",
        "Vice President",
    )
    await pay_office(
        getattr(nation, "speaker_character_id", None),
        "speaker",
        "last_speaker_salary_at",
        "Speaker",
    )

    # Ministers
    seats = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.is_npc.is_(False),
            CabinetSeat.character_id.is_not(None),
        )
    )
    for seat in seats.scalars().all():
        last = seat.last_salary_at or seat.appointed_at
        if not _due(last, now):
            continue
        ch = await db.get(Character, seat.character_id)
        if ch is None:
            continue
        info = weekly_gross("minister", ch)
        funded = await _pay_character(
            db,
            ch,
            info["gross"],
            note=f"Minister weekly pay — {seat.title}"
            + (" (scandal cut)" if info["scandal"] else ""),
        )
        seat.last_salary_at = now
        paid["ministers"] += funded
        if funded:
            paid["count"] += 1

    # MPs
    states = await db.execute(
        select(State).where(State.mp_character_id.is_not(None))
    )
    for state in states.scalars().all():
        if not _due(getattr(state, "last_mp_salary_at", None), now):
            continue
        ch = await db.get(Character, state.mp_character_id)
        if ch is None:
            continue
        info = weekly_gross("mp", ch)
        funded = await _pay_character(
            db,
            ch,
            info["gross"],
            note=f"MP weekly pay — {state.name}"
            + (" (scandal cut)" if info["scandal"] else ""),
        )
        state.last_mp_salary_at = now
        paid["mps"] += funded
        if funded:
            paid["count"] += 1

    if paid["count"]:
        await db.flush()
    return paid


async def pay_session_bonus(
    db: AsyncSession, character: Character, *, kind: str = "bill"
) -> float:
    """Sitting stipend when an MP (or minister) participates in a vote."""
    settings = get_settings()
    amount = 0.0
    # MP session
    mp_state = await db.execute(
        select(State).where(State.mp_character_id == character.id).limit(1)
    )
    if mp_state.scalar_one_or_none() is not None:
        amount = max(amount, settings.office_session_bonus_mp)
    # Minister session (cabinet holders)
    seat = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.character_id == character.id,
            CabinetSeat.is_npc.is_(False),
        )
    )
    if seat.scalar_one_or_none() is not None:
        amount = max(amount, settings.office_session_bonus_minister)
    if amount <= 0:
        return 0.0
    if scandal_applies(character):
        amount = round(amount * settings.office_scandal_pay_factor, 2)
    return await _pay_character(
        db,
        character,
        amount,
        note=f"Session stipend ({kind})",
    )


async def pay_budget_passed_bonuses(db: AsyncSession, budget_id: int) -> dict:
    settings = get_settings()
    from app.services import politics_service

    nation = await politics_service.get_or_create_nation(db)
    paid = {"president": 0.0, "finance": 0.0, "mps": 0.0}

    if nation.president_character_id:
        ch = await db.get(Character, nation.president_character_id)
        if ch:
            amt = settings.office_budget_bonus_president
            if scandal_applies(ch):
                amt = round(amt * settings.office_scandal_pay_factor, 2)
            paid["president"] = await _pay_character(
                db, ch, amt, note="Budget passed bonus — President"
            )

    finance = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.portfolio == Portfolio.FINANCE,
            CabinetSeat.is_npc.is_(False),
            CabinetSeat.character_id.is_not(None),
        )
    )
    seat = finance.scalar_one_or_none()
    if seat and seat.character_id:
        ch = await db.get(Character, seat.character_id)
        if ch:
            amt = settings.office_budget_bonus_finance
            if scandal_applies(ch):
                amt = round(amt * settings.office_scandal_pay_factor, 2)
            paid["finance"] = await _pay_character(
                db, ch, amt, note="Budget passed bonus — Finance"
            )

    yes_votes = await db.execute(
        select(BudgetVote).where(
            BudgetVote.budget_id == budget_id,
            BudgetVote.choice == BillVoteChoice.YES,
        )
    )
    for vote in yes_votes.scalars().all():
        ch = await db.get(Character, vote.character_id)
        if ch is None:
            continue
        amt = settings.office_budget_bonus_mp_yes
        if scandal_applies(ch):
            amt = round(amt * settings.office_scandal_pay_factor, 2)
        paid["mps"] += await _pay_character(
            db, ch, amt, note="Budget passed bonus — MP yes vote"
        )

    await db.flush()
    return paid


async def pay_election_win_bonuses(
    db: AsyncSession,
    *,
    president_character_id: int | None,
    mp_character_ids: list[int],
) -> dict:
    settings = get_settings()
    paid = {"president": 0.0, "mps": 0.0}
    if president_character_id:
        ch = await db.get(Character, president_character_id)
        if ch:
            amt = settings.office_election_bonus_president
            if scandal_applies(ch):
                amt = round(amt * settings.office_scandal_pay_factor, 2)
            paid["president"] = await _pay_character(
                db, ch, amt, note="Election victory bonus — President"
            )
    for cid in mp_character_ids:
        ch = await db.get(Character, cid)
        if ch is None:
            continue
        amt = settings.office_election_bonus_mp
        if scandal_applies(ch):
            amt = round(amt * settings.office_scandal_pay_factor, 2)
        paid["mps"] += await _pay_character(
            db, ch, amt, note="Election victory bonus — MP"
        )
    await db.flush()
    return paid


async def political_office_keys(
    db: AsyncSession, character: Character
) -> list[str]:
    """Keys for political offices this character currently holds."""
    from app.services import politics_service

    nation = await politics_service.get_or_create_nation(db)
    keys: list[str] = []
    if nation.president_character_id == character.id:
        keys.append("president")
    if getattr(nation, "vice_president_character_id", None) == character.id:
        keys.append("vice_president")
    if getattr(nation, "speaker_character_id", None) == character.id:
        keys.append("speaker")
    seat_q = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.character_id == character.id,
            CabinetSeat.is_npc.is_(False),
        )
    )
    if seat_q.scalar_one_or_none():
        keys.append("minister")
    mp_q = await db.execute(
        select(State.id).where(State.mp_character_id == character.id).limit(1)
    )
    if mp_q.scalar_one_or_none() is not None:
        keys.append("mp")
    return keys


async def holds_political_office(db: AsyncSession, character: Character) -> bool:
    return bool(await political_office_keys(db, character))


EMPLOYEE_JOB_BLOCKED_BY_OFFICE = (
    "Political office holders cannot work as employees "
    "(state jobs or company payroll). You may still own companies and businesses."
)


async def end_employee_jobs_for_office(
    db: AsyncSession,
    character: Character,
    *,
    reason: str = "Took political office",
) -> dict:
    """
    End state + company employee roles. Does not touch owned businesses.
    """
    from app.models.business import Business
    from app.models.employee import BusinessEmployee
    from app.services import job_service, notify_service

    left_state = await job_service.resign_current_job(db, character)
    left_companies: list[int] = []
    result = await db.execute(
        select(BusinessEmployee).where(
            BusinessEmployee.character_id == character.id,
            BusinessEmployee.is_active.is_(True),
            BusinessEmployee.is_npc.is_(False),
        )
    )
    for emp in result.scalars().all():
        emp.is_active = False
        left_companies.append(emp.business_id)
        biz = await db.get(Business, emp.business_id)
        if biz and biz.owner_id != character.id:
            await notify_service.push(
                db,
                biz.owner_id,
                f"{character.display_name} left {biz.name}",
                body=reason,
                category="job",
            )
    if left_state or left_companies:
        await db.flush()
    return {
        "left_state_job": left_state,
        "left_company_jobs": left_companies,
    }


async def my_office_pay(db: AsyncSession, character: Character) -> dict:
    """What this character currently earns from political office."""
    roles: list[dict] = []
    keys = await political_office_keys(db, character)
    if "president" in keys:
        roles.append(weekly_gross("president", character))
    if "vice_president" in keys:
        roles.append(weekly_gross("vice_president", character))
    if "speaker" in keys:
        roles.append(weekly_gross("speaker", character))

    if "minister" in keys:
        seat_q = await db.execute(
            select(CabinetSeat).where(CabinetSeat.character_id == character.id)
        )
        seat = seat_q.scalar_one_or_none()
        if seat:
            info = weekly_gross("minister", character)
            info["title"] = seat.title
            info["portfolio"] = seat.portfolio.value
            roles.append(info)

    if "mp" in keys:
        mp_q = await db.execute(
            select(State).where(State.mp_character_id == character.id)
        )
        for st in mp_q.scalars().all():
            info = weekly_gross("mp", character)
            info["state_id"] = st.id
            info["state_name"] = st.name
            roles.append(info)

    weekly = round(sum(float(r["gross"]) for r in roles), 2)
    return {
        "roles": roles,
        "weekly_gross": weekly,
        "blocks_employee_jobs": bool(roles),
        "catalog": office_pay_catalog(),
    }
