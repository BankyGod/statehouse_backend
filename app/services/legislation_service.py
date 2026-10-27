from datetime import timedelta
import random

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.models.legislation import (
    Bill,
    BillStatus,
    BillVote,
    BillVoteChoice,
    BudgetReading,
    BudgetStatus,
    BudgetVote,
)
from app.models.state import State
from app.services import news_service, politics_service
from app.services.character_service import ensure_can_act

MAJORITY = 11


def _aware(dt):
    if dt is not None and getattr(dt, "tzinfo", None) is None:
        from datetime import timezone

        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _require_mp(db: AsyncSession, character: Character) -> State:
    result = await db.execute(
        select(State).where(State.mp_character_id == character.id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        raise HTTPException(status_code=403, detail="Only sitting MPs can do this")
    return state


async def _npc_mp_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(State).where(State.mp_character_id.is_(None))
    )
    return int(result.scalar_one())


def _infer_bill_effect(title: str, summary: str) -> tuple[str | None, float | None]:
    """Map common bill language to living-world effects."""
    text = f"{title} {summary}".lower()
    if any(w in text for w in ("police", "crime", "security", "catch")):
        return "crime_catch_delta", 0.03
    if any(w in text for w in ("tax cut", "tax relief", "lower tax")):
        return "national_tax_delta", -0.005
    if any(w in text for w in ("tax hike", "raise tax", "revenue act")):
        return "national_tax_delta", 0.005
    if any(w in text for w in ("education", "university", "tuition", "school")):
        return "education_subsidy", 0.10
    if any(w in text for w in ("transport", "rail", "fare", "port")):
        return "travel_cost_mult", 0.95
    if any(w in text for w in ("energy", "power", "grid")):
        return "energy_grid_fee", 0.5
    return None, None


async def apply_enacted_bill(db: AsyncSession, bill: Bill) -> dict:
    """Apply real rule changes when a bill becomes law."""
    from app.services import politics_service, treasury_service

    key = bill.effect_key
    val = bill.effect_value
    if not key:
        key, val = _infer_bill_effect(bill.title, bill.summary)
        bill.effect_key = key
        bill.effect_value = val
    if not key or val is None:
        return {"applied": False}

    applied: dict = {"effect_key": key, "effect_value": val, "applied": True}
    if key == "crime_catch_delta":
        states = (await db.execute(select(State))).scalars().all()
        for st in states:
            st.crime_catch_rate = round(
                min(0.85, max(0.10, float(st.crime_catch_rate) + float(val))), 4
            )
        applied["states"] = len(states)
    elif key == "national_tax_delta":
        nation = await politics_service.get_or_create_nation(db)
        settings = get_settings()
        new_rate = float(nation.national_tax_rate or 0.05) + float(val)
        new_rate = max(settings.min_national_tax_rate, min(settings.max_national_tax_rate, new_rate))
        await treasury_service.set_national_tax_rate(db, new_rate)
        applied["national_tax_rate"] = new_rate
    elif key == "education_subsidy":
        # Store as nation note flag; enroll discounts read via get_settings override
        nation = await politics_service.get_or_create_nation(db)
        nation.notes = (nation.notes or "") + f"|edu_subsidy={float(val):.3f}"
        applied["education_subsidy"] = float(val)
    elif key == "travel_cost_mult":
        nation = await politics_service.get_or_create_nation(db)
        nation.notes = (nation.notes or "") + f"|travel_mult={float(val):.3f}"
        applied["travel_cost_mult"] = float(val)
    elif key == "energy_grid_fee":
        from app.models.enterprise import EnterpriseKind, StateEnterprise

        ent = (
            await db.execute(
                select(StateEnterprise).where(
                    StateEnterprise.kind == EnterpriseKind.POWER
                )
            )
        ).scalar_one_or_none()
        if ent:
            fee = round(float(val) * 1000, 2)
            ent.cash_balance = round(float(ent.cash_balance or 0) + fee, 2)
            ent.lifetime_revenue = round(float(ent.lifetime_revenue or 0) + fee, 2)
            applied["energy_credit"] = fee
    await db.flush()
    return applied


async def propose_bill(
    db: AsyncSession,
    character: Character,
    title: str,
    summary: str,
    *,
    effect_key: str | None = None,
    effect_value: float | None = None,
) -> Bill:
    ensure_can_act(character)
    state = await _require_mp(db, character)
    settings = get_settings()
    now = utcnow()
    npc_count = await _npc_mp_count(db)
    npc_yes = int(npc_count * 0.55) if npc_count else 0
    npc_no = npc_count - npc_yes

    if not effect_key:
        effect_key, effect_value = _infer_bill_effect(title, summary)

    bill = Bill(
        title=title.strip()[:160],
        summary=summary.strip(),
        sponsor_character_id=character.id,
        sponsor_state_id=state.id,
        status=BillStatus.DEBATE,
        npc_yes=npc_yes,
        npc_no=npc_no,
        debate_ends_at=now + timedelta(days=settings.bill_debate_days),
        effect_key=effect_key,
        effect_value=effect_value,
    )
    db.add(bill)
    await db.flush()
    await news_service.publish(
        db,
        f"Bill tabled: {bill.title}",
        f"MP for {state.name} introduced a bill. Debate closes in "
        f"{settings.bill_debate_days} days.",
        category="politics",
        state_id=state.id,
    )
    await db.refresh(bill)
    return bill


async def vote_on_bill(
    db: AsyncSession, character: Character, bill_id: int, choice: BillVoteChoice
) -> dict:
    ensure_can_act(character)
    await _require_mp(db, character)
    bill = await db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status != BillStatus.DEBATE:
        raise HTTPException(status_code=400, detail="Bill is not in debate")

    existing = await db.execute(
        select(BillVote).where(
            BillVote.bill_id == bill_id, BillVote.character_id == character.id
        )
    )
    prior = existing.scalar_one_or_none()
    if prior:
        if prior.choice == BillVoteChoice.YES:
            bill.yes_votes = max(0, bill.yes_votes - 1)
        elif prior.choice == BillVoteChoice.NO:
            bill.no_votes = max(0, bill.no_votes - 1)
        else:
            bill.abstain_votes = max(0, bill.abstain_votes - 1)
        prior.choice = choice
    else:
        db.add(BillVote(bill_id=bill_id, character_id=character.id, choice=choice))

    if choice == BillVoteChoice.YES:
        bill.yes_votes += 1
    elif choice == BillVoteChoice.NO:
        bill.no_votes += 1
    else:
        bill.abstain_votes += 1

    session_bonus = 0.0
    if prior is None:
        from app.services import office_pay_service

        session_bonus = await office_pay_service.pay_session_bonus(
            db, character, kind="bill"
        )

    await db.flush()
    return {
        "bill_id": bill.id,
        "choice": choice.value,
        "yes_votes": bill.yes_votes,
        "no_votes": bill.no_votes,
        "abstain_votes": bill.abstain_votes,
        "npc_yes": bill.npc_yes,
        "npc_no": bill.npc_no,
        "session_bonus": session_bonus,
    }


def _total_yes(bill: Bill) -> int:
    return bill.yes_votes + bill.npc_yes


def _total_no(bill: Bill) -> int:
    return bill.no_votes + bill.npc_no


async def resolve_due_bills(db: AsyncSession) -> int:
    now = utcnow()
    result = await db.execute(select(Bill).where(Bill.status == BillStatus.DEBATE))
    resolved = 0
    for bill in result.scalars().all():
        if _aware(bill.debate_ends_at) > now:
            continue

        yes = _total_yes(bill)
        no = _total_no(bill)
        if yes >= MAJORITY and yes > no:
            nation = await politics_service.get_or_create_nation(db)
            if nation.president_character_id is None and random.random() < 0.2:
                bill.status = BillStatus.VETOED
                bill.vetoed = True
                await news_service.publish(
                    db,
                    f"Presidential veto: {bill.title}",
                    "The President rejected the bill.",
                    category="politics",
                )
            else:
                bill.status = BillStatus.ENACTED
                bill.enacted_at = now
                effect = await apply_enacted_bill(db, bill)
                effect_note = ""
                if effect.get("applied"):
                    effect_note = (
                        f" Effect: {effect.get('effect_key')}="
                        f"{effect.get('effect_value')}."
                    )
                await news_service.publish(
                    db,
                    f"Law enacted: {bill.title}",
                    (bill.summary[:360] + effect_note)[:400],
                    category="politics",
                )
        else:
            bill.status = BillStatus.FAILED
            await news_service.publish(
                db,
                f"Bill failed: {bill.title}",
                f"Final tally yes {yes} / no {no}.",
                category="politics",
            )
        resolved += 1
    if resolved:
        await db.flush()
    return resolved


async def list_bills(db: AsyncSession, status: str | None = None) -> list[Bill]:
    stmt = select(Bill).order_by(Bill.id.desc()).limit(50)
    if status:
        stmt = stmt.where(Bill.status == BillStatus(status))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def veto_bill(db: AsyncSession, character: Character, bill_id: int) -> Bill:
    ensure_can_act(character)
    nation = await politics_service.get_or_create_nation(db)
    if nation.president_character_id != character.id:
        raise HTTPException(status_code=403, detail="Only the President can veto")
    bill = await db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status not in (BillStatus.PASSED, BillStatus.ENACTED):
        raise HTTPException(status_code=400, detail="Bill cannot be vetoed in this state")
    bill.status = BillStatus.VETOED
    bill.vetoed = True
    bill.enacted_at = None
    await news_service.publish(
        db,
        f"Veto: {bill.title}",
        f"President {character.display_name} vetoed the bill.",
        category="politics",
    )
    await db.flush()
    await db.refresh(bill)
    return bill


async def _open_budget(db: AsyncSession) -> BudgetReading:
    settings = get_settings()
    now = utcnow()
    rate = round(
        random.uniform(settings.min_national_tax_rate, settings.max_national_tax_rate),
        3,
    )
    budget = BudgetReading(
        title=f"National Budget {now.strftime('%b %Y')}",
        summary=(
            f"Proposed national tax rate {rate:.1%}. "
            "MPs must approve before the reading closes."
        ),
        national_tax_rate=rate,
        status=BudgetStatus.OPEN,
        opens_at=now,
        closes_at=now + timedelta(days=settings.budget_debate_days),
    )
    db.add(budget)
    await db.flush()
    await news_service.publish(db, budget.title, budget.summary, category="economy")
    await db.refresh(budget)
    return budget


async def resolve_due_budgets(db: AsyncSession) -> int:
    now = utcnow()
    result = await db.execute(
        select(BudgetReading).where(BudgetReading.status == BudgetStatus.OPEN)
    )
    count = 0
    for budget in result.scalars().all():
        if _aware(budget.closes_at) > now:
            continue
        npc = await _npc_mp_count(db)
        npc_yes = int(npc * 0.6)
        total_yes = budget.yes_votes + npc_yes
        total_no = budget.no_votes + (npc - npc_yes)
        if total_yes >= MAJORITY and total_yes > total_no:
            budget.status = BudgetStatus.PASSED
            from app.services import office_pay_service, treasury_service

            await treasury_service.set_national_tax_rate(
                db, budget.national_tax_rate
            )
            await office_pay_service.pay_budget_passed_bonuses(db, budget.id)
            from app.services import stock_service

            await stock_service.apply_budget_market_shock(
                db, tax_rate=budget.national_tax_rate
            )
            await news_service.publish(
                db,
                f"Budget passed: {budget.title}",
                f"National tax rate set to {budget.national_tax_rate:.1%}.",
                category="economy",
            )
        else:
            budget.status = BudgetStatus.REJECTED
            await news_service.publish(
                db,
                f"Budget rejected: {budget.title}",
                "Parliament rejected the reading.",
                category="economy",
            )
        budget.resolved_at = now
        count += 1
    if count:
        await db.flush()
    return count


async def get_current_budget(db: AsyncSession) -> BudgetReading | None:
    await resolve_due_budgets(db)

    open_result = await db.execute(
        select(BudgetReading)
        .where(BudgetReading.status == BudgetStatus.OPEN)
        .order_by(BudgetReading.id.desc())
        .limit(1)
    )
    current = open_result.scalar_one_or_none()
    if current:
        return current

    settings = get_settings()
    last_result = await db.execute(
        select(BudgetReading).order_by(BudgetReading.id.desc()).limit(1)
    )
    previous = last_result.scalar_one_or_none()
    now = utcnow()

    if previous is None:
        return await _open_budget(db)

    anchor = _aware(previous.resolved_at or previous.closes_at)
    if now >= anchor + timedelta(days=settings.budget_interval_days):
        return await _open_budget(db)
    return None


async def vote_on_budget(
    db: AsyncSession, character: Character, budget_id: int, choice: BillVoteChoice
) -> dict:
    ensure_can_act(character)
    await _require_mp(db, character)
    budget = await db.get(BudgetReading, budget_id)
    if budget is None or budget.status != BudgetStatus.OPEN:
        raise HTTPException(status_code=400, detail="No open budget reading")
    if choice == BillVoteChoice.ABSTAIN:
        raise HTTPException(status_code=400, detail="Budget votes must be yes or no")

    existing = await db.execute(
        select(BudgetVote).where(
            BudgetVote.budget_id == budget_id,
            BudgetVote.character_id == character.id,
        )
    )
    prior = existing.scalar_one_or_none()
    if prior:
        if prior.choice == BillVoteChoice.YES:
            budget.yes_votes = max(0, budget.yes_votes - 1)
        else:
            budget.no_votes = max(0, budget.no_votes - 1)
        prior.choice = choice
    else:
        db.add(
            BudgetVote(budget_id=budget_id, character_id=character.id, choice=choice)
        )

    if choice == BillVoteChoice.YES:
        budget.yes_votes += 1
    else:
        budget.no_votes += 1

    session_bonus = 0.0
    if prior is None:
        from app.services import office_pay_service

        session_bonus = await office_pay_service.pay_session_bonus(
            db, character, kind="budget"
        )

    await db.flush()
    return {
        "budget_id": budget.id,
        "choice": choice.value,
        "yes_votes": budget.yes_votes,
        "no_votes": budget.no_votes,
        "session_bonus": session_bonus,
    }
