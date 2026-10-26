"""National treasury bank account — all taxes and government fees land here."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.cabinet import CabinetSeat, Portfolio
from app.models.character import Character
from app.models.politics import NationOffice
from app.models.state import State
from app.models.treasury import TreasuryTransaction, TreasuryTxType
from app.services.politics_service import get_or_create_nation

DEFAULT_SEED_TREASURY = 100_000.0


async def get_nation(db: AsyncSession) -> NationOffice:
    nation = await get_or_create_nation(db)
    balance = getattr(nation, "treasury_balance", None)
    if balance is None:
        nation.treasury_balance = DEFAULT_SEED_TREASURY
        await db.flush()
    rate = getattr(nation, "national_tax_rate", None)
    if rate is None:
        nation.national_tax_rate = get_settings().default_national_tax_rate
        await db.flush()
    return nation


async def get_tax_rate(db: AsyncSession, character: Character | None = None) -> float:
    """Moderate income-tax rate (national + light state vibe, capped)."""
    settings = get_settings()
    nation = await get_nation(db)
    national = float(nation.national_tax_rate or settings.default_national_tax_rate)
    if character is None:
        return round(
            max(settings.min_national_tax_rate, min(national, settings.max_national_tax_rate)),
            4,
        )
    state = await db.get(State, character.home_state_id)
    state_vibe = min(float(state.base_tax_rate if state else 0.05), 0.08)
    # Mostly national; state only nudges a little
    blended = (national * 0.85) + (state_vibe * 0.15)
    return round(
        max(settings.min_national_tax_rate, min(blended, settings.max_national_tax_rate)),
        4,
    )


async def get_corporate_tax_rate(db: AsyncSession) -> float:
    settings = get_settings()
    nation = await get_nation(db)
    national = float(nation.national_tax_rate or settings.default_national_tax_rate)
    corp = national * settings.corporate_tax_multiplier
    return round(max(0.02, min(corp, settings.max_national_tax_rate)), 4)


async def office_roles(db: AsyncSession, character: Character) -> dict:
    """Who this character is in government (for treasury ACL)."""
    nation = await get_nation(db)
    is_president = nation.president_character_id == character.id
    is_vp = getattr(nation, "vice_president_character_id", None) == character.id
    is_speaker = getattr(nation, "speaker_character_id", None) == character.id

    mp_row = await db.execute(
        select(State.id, State.name).where(State.mp_character_id == character.id)
    )
    mp = mp_row.first()
    is_mp = mp is not None

    cab = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.character_id == character.id,
            CabinetSeat.is_npc.is_(False),
        )
    )
    seats = list(cab.scalars().all())
    portfolios = [s.portfolio for s in seats]
    is_minister = len(seats) > 0
    is_finance = Portfolio.FINANCE in portfolios

    can_view = is_president or is_vp or is_speaker or is_mp or is_minister
    can_spend = is_president or is_finance

    roles: list[str] = []
    if is_president:
        roles.append("president")
    if is_vp:
        roles.append("vice_president")
    if is_speaker:
        roles.append("speaker")
    if is_mp:
        roles.append(f"mp:{mp[1]}")
    for s in seats:
        roles.append(f"minister:{s.portfolio.value}")

    return {
        "can_view": can_view,
        "can_spend": can_spend,
        "is_president": is_president,
        "is_finance_minister": is_finance,
        "roles": roles,
    }


async def require_treasury_viewer(db: AsyncSession, character: Character) -> dict:
    access = await office_roles(db, character)
    if not access["can_view"]:
        raise HTTPException(
            status_code=403,
            detail="Only the President, Vice President, Speaker, MPs, and ministers can view the national treasury",
        )
    return access


async def require_treasury_spender(db: AsyncSession, character: Character) -> dict:
    access = await require_treasury_viewer(db, character)
    if not access["can_spend"]:
        raise HTTPException(
            status_code=403,
            detail="Only the President or Minister of Finance can disburse treasury funds",
        )
    return access


async def credit(
    db: AsyncSession,
    amount: float,
    tx_type: TreasuryTxType,
    *,
    note: str | None = None,
    character_id: int | None = None,
    business_id: int | None = None,
) -> float:
    """Add money to the country treasury. Returns new balance."""
    amount = round(float(amount), 2)
    if amount <= 0:
        nation = await get_nation(db)
        return float(nation.treasury_balance or 0)
    nation = await get_nation(db)
    nation.treasury_balance = round(float(nation.treasury_balance or 0) + amount, 2)
    db.add(
        TreasuryTransaction(
            tx_type=tx_type,
            amount=amount,
            balance_after=nation.treasury_balance,
            character_id=character_id,
            business_id=business_id,
            note=note,
            posted_at=utcnow(),
        )
    )
    await db.flush()
    return nation.treasury_balance


async def debit(
    db: AsyncSession,
    amount: float,
    tx_type: TreasuryTxType,
    *,
    note: str | None = None,
    character_id: int | None = None,
    allow_overdraft: bool = True,
) -> float:
    """Pay from treasury (e.g. public salaries). Returns amount actually paid."""
    amount = round(float(amount), 2)
    if amount <= 0:
        return 0.0
    nation = await get_nation(db)
    bal = float(nation.treasury_balance or 0)
    if not allow_overdraft and bal < amount:
        amount = round(bal, 2)
        if amount <= 0:
            return 0.0
    nation.treasury_balance = round(bal - amount, 2)
    db.add(
        TreasuryTransaction(
            tx_type=tx_type,
            amount=-amount,
            balance_after=nation.treasury_balance,
            character_id=character_id,
            note=note,
            posted_at=utcnow(),
        )
    )
    await db.flush()
    return amount


async def pay_taxable_income(
    db: AsyncSession,
    character: Character,
    gross: float,
    *,
    note: str,
) -> dict:
    """Credit net wages to character cash; income tax → treasury; garnish welfare loans."""
    gross = round(float(gross), 2)
    if gross <= 0:
        return {
            "gross": 0.0,
            "tax": 0.0,
            "net": 0.0,
            "rate": 0.0,
            "loan_repaid": 0.0,
        }
    rate = await get_tax_rate(db, character)
    tax = round(gross * rate, 2)
    net = round(gross - tax, 2)
    character.cash = round(float(character.cash) + net, 2)
    if tax > 0:
        await credit(
            db,
            tax,
            TreasuryTxType.INCOME_TAX,
            note=note,
            character_id=character.id,
        )

    loan_repaid = 0.0
    from app.models.loan import Loan, LoanKind, LoanStatus

    result = await db.execute(
        select(Loan).where(
            Loan.character_id == character.id,
            Loan.status == LoanStatus.ACTIVE,
            Loan.auto_repay.is_(True),
        )
    )
    for loan in result.scalars().all():
        pct = float(loan.repay_pct_of_gross or 0)
        if pct <= 0:
            continue
        take = round(min(gross * pct, loan.remaining, character.cash), 2)
        if take <= 0:
            continue
        character.cash = round(float(character.cash) - take, 2)
        loan.remaining = round(float(loan.remaining) - take, 2)
        loan.payments_made = int(loan.payments_made or 0) + 1
        loan_repaid = round(loan_repaid + take, 2)
        if loan.loan_kind == LoanKind.HOUSING_WELFARE.value:
            await credit(
                db,
                take,
                TreasuryTxType.TRANSFER,
                note=f"Housing welfare repayment — loan #{loan.id}",
                character_id=character.id,
            )
        if loan.remaining <= 0.009:
            loan.remaining = 0.0
            loan.status = LoanStatus.PAID
    if loan_repaid:
        await db.flush()

    return {
        "gross": gross,
        "tax": tax,
        "net": round(net - loan_repaid, 2),
        "rate": rate,
        "loan_repaid": loan_repaid,
    }


async def take_corporate_tax(
    db: AsyncSession,
    gross_revenue: float,
    *,
    business_id: int,
    note: str,
) -> dict:
    """Split business revenue: net stays with company, tax → treasury."""
    gross = round(float(gross_revenue), 2)
    if gross <= 0:
        return {"gross": 0.0, "tax": 0.0, "net": 0.0, "rate": 0.0}
    rate = await get_corporate_tax_rate(db)
    tax = round(gross * rate, 2)
    net = round(gross - tax, 2)
    if tax > 0:
        await credit(
            db,
            tax,
            TreasuryTxType.CORPORATE_TAX,
            note=note,
            business_id=business_id,
        )
    return {"gross": gross, "tax": tax, "net": net, "rate": rate}


async def collect_fee(
    db: AsyncSession,
    amount: float,
    *,
    note: str,
    character_id: int | None = None,
    tx_type: TreasuryTxType = TreasuryTxType.FEE,
) -> float:
    """Route a government fee/fine/bail into the treasury (caller already charged payer)."""
    return await credit(
        db,
        amount,
        tx_type,
        note=note,
        character_id=character_id,
    )


async def set_national_tax_rate(db: AsyncSession, rate: float) -> float:
    settings = get_settings()
    nation = await get_nation(db)
    nation.national_tax_rate = round(
        max(settings.min_national_tax_rate, min(float(rate), settings.max_national_tax_rate)),
        4,
    )
    await db.flush()
    return nation.national_tax_rate


async def disburse(
    db: AsyncSession,
    actor: Character,
    *,
    amount: float,
    reason: str,
    to_character_id: int | None = None,
    to_display_name: str | None = None,
) -> dict:
    """
    Controlled spend: President or Finance Minister only.
    Pays cash to a recipient (grant / appropriation) — fully ledgered.
    """
    access = await require_treasury_spender(db, actor)
    settings = get_settings()
    amount = round(float(amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if amount > settings.treasury_max_disburse:
        raise HTTPException(
            status_code=400,
            detail=f"Max disbursement is ${settings.treasury_max_disburse:.0f} per transfer",
        )
    reason = (reason or "").strip()
    if len(reason) < 8:
        raise HTTPException(status_code=400, detail="Reason required (min 8 characters)")

    recipient: Character | None = None
    if to_character_id is not None:
        recipient = await db.get(Character, to_character_id)
    elif to_display_name:
        result = await db.execute(
            select(Character).where(Character.display_name == to_display_name.strip())
        )
        recipient = result.scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status_code=404, detail="Recipient character not found")

    nation = await get_nation(db)
    bal = float(nation.treasury_balance or 0)
    if bal < amount:
        raise HTTPException(
            status_code=400,
            detail=f"Treasury has only ${bal:.2f}",
        )

    who = "President" if access["is_president"] else "Minister of Finance"
    note = f"{who} disbursement to {recipient.display_name}: {reason[:180]}"
    paid = await debit(
        db,
        amount,
        TreasuryTxType.TRANSFER,
        note=note,
        character_id=actor.id,
        allow_overdraft=False,
    )
    recipient.cash = round(float(recipient.cash) + paid, 2)
    await db.flush()

    from app.services import notify_service

    await notify_service.push(
        db,
        recipient.id,
        "Treasury disbursement",
        body=f"+${paid:.2f} — {reason[:120]}",
        category="treasury",
    )
    return {
        "disbursed": paid,
        "to_character_id": recipient.id,
        "to_display_name": recipient.display_name,
        "reason": reason[:255],
        "treasury_balance": float((await get_nation(db)).treasury_balance or 0),
        "authorized_by": who,
    }


async def donate(
    db: AsyncSession,
    actor: Character,
    *,
    amount: float,
    note: str | None = None,
) -> dict:
    """President or Finance Minister may inject personal cash into the treasury."""
    await require_treasury_spender(db, actor)
    amount = round(float(amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if actor.cash < amount:
        raise HTTPException(status_code=400, detail="Insufficient personal cash")
    actor.cash = round(float(actor.cash) - amount, 2)
    bal = await credit(
        db,
        amount,
        TreasuryTxType.ADJUSTMENT,
        note=(note or f"Donation by {actor.display_name}")[:255],
        character_id=actor.id,
    )
    return {"donated": amount, "treasury_balance": bal, "cash": actor.cash}


async def treasury_snapshot(
    db: AsyncSession, character: Character, *, limit: int = 40
) -> dict:
    access = await require_treasury_viewer(db, character)
    nation = await get_nation(db)
    result = await db.execute(
        select(TreasuryTransaction)
        .order_by(TreasuryTransaction.id.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    settings = get_settings()
    return {
        "account_name": "United Amir National Treasury",
        "balance": float(nation.treasury_balance or 0),
        "national_tax_rate": float(
            nation.national_tax_rate or settings.default_national_tax_rate
        ),
        "corporate_tax_rate": await get_corporate_tax_rate(db),
        "your_access": {
            "can_view": True,
            "can_spend": access["can_spend"],
            "roles": access["roles"],
        },
        "spend_rules": {
            "who": "President or Minister of Finance only",
            "max_per_transfer": settings.treasury_max_disburse,
            "note": "MPs and other ministers can view the ledger but cannot move funds.",
        },
        "transactions": [
            {
                "id": t.id,
                "tx_type": t.tx_type.value,
                "amount": t.amount,
                "balance_after": t.balance_after,
                "character_id": t.character_id,
                "business_id": t.business_id,
                "note": t.note,
                "posted_at": t.posted_at,
            }
            for t in rows
        ],
    }
