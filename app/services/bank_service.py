from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.bank import BankTransaction, BankTxType
from app.models.character import Character
from app.models.loan import Loan, LoanStatus
from app.services.character_service import ensure_can_act


async def _ledger(
    db: AsyncSession,
    character: Character,
    tx_type: BankTxType,
    amount: float,
    *,
    note: str | None = None,
    counterparty_id: int | None = None,
) -> None:
    db.add(
        BankTransaction(
            character_id=character.id,
            tx_type=tx_type,
            amount=amount,
            balance_after=round(character.bank_balance, 2),
            counterparty_id=counterparty_id,
            note=note,
            posted_at=utcnow(),
        )
    )


async def apply_savings_interest(db: AsyncSession, character: Character) -> float:
    """Daily compound-ish interest on bank_balance (APR / 365)."""
    if character.bank_balance <= 0:
        character.last_bank_interest_at = utcnow()
        return 0.0

    settings = get_settings()
    now = utcnow()
    last = character.last_bank_interest_at or character.created_at or now
    if last.tzinfo is None:
        from datetime import timezone

        last = last.replace(tzinfo=timezone.utc)

    days = (now - last).total_seconds() / 86400.0
    if days < 1.0:
        return 0.0

    daily_rate = settings.savings_apr / 365.0
    interest = round(character.bank_balance * ((1 + daily_rate) ** int(days) - 1), 2)
    if interest <= 0:
        character.last_bank_interest_at = now
        return 0.0

    character.bank_balance = round(character.bank_balance + interest, 2)
    character.last_bank_interest_at = now
    await _ledger(
        db, character, BankTxType.INTEREST, interest, note=f"Savings interest ({int(days)}d)"
    )
    await db.flush()
    return interest


async def deposit(db: AsyncSession, character: Character, amount: float) -> dict:
    ensure_can_act(character, require_housing=False)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if character.cash < amount:
        raise HTTPException(status_code=400, detail="Insufficient cash")
    character.cash -= amount
    character.bank_balance += amount
    await _ledger(db, character, BankTxType.DEPOSIT, amount, note="Cash deposit")
    await db.flush()
    return {
        "cash": round(character.cash, 2),
        "bank_balance": round(character.bank_balance, 2),
        "moved": amount,
    }


async def withdraw(db: AsyncSession, character: Character, amount: float) -> dict:
    ensure_can_act(character, require_housing=False)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if character.bank_balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient bank balance")
    character.bank_balance -= amount
    character.cash += amount
    await _ledger(db, character, BankTxType.WITHDRAW, amount, note="Cash withdrawal")
    await db.flush()
    return {
        "cash": round(character.cash, 2),
        "bank_balance": round(character.bank_balance, 2),
        "moved": amount,
    }


async def transfer(
    db: AsyncSession, character: Character, to_display_name: str, amount: float
) -> dict:
    """Bank-to-bank transfer between players (fee deducted from sender bank)."""
    ensure_can_act(character, require_housing=False)
    settings = get_settings()
    if amount < settings.bank_min_transfer:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum transfer is ${settings.bank_min_transfer:.0f}",
        )

    total = amount + settings.bank_transfer_fee
    if character.bank_balance < total:
        raise HTTPException(
            status_code=400,
            detail=f"Need ${total:.2f} in bank (amount + ${settings.bank_transfer_fee:.0f} fee)",
        )

    result = await db.execute(
        select(Character).where(Character.display_name == to_display_name.strip())
    )
    other = result.scalar_one_or_none()
    if other is None:
        raise HTTPException(status_code=404, detail="Recipient character not found")
    if other.id == character.id:
        raise HTTPException(status_code=400, detail="Cannot transfer to yourself")

    character.bank_balance = round(character.bank_balance - total, 2)
    other.bank_balance = round(other.bank_balance + amount, 2)

    await _ledger(
        db,
        character,
        BankTxType.TRANSFER_OUT,
        amount,
        note=f"To {other.display_name}",
        counterparty_id=other.id,
    )
    await _ledger(
        db,
        character,
        BankTxType.FEE,
        settings.bank_transfer_fee,
        note="Transfer fee",
        counterparty_id=other.id,
    )
    await _ledger(
        db,
        other,
        BankTxType.TRANSFER_IN,
        amount,
        note=f"From {character.display_name}",
        counterparty_id=character.id,
    )
    await db.flush()
    return {
        "sent": amount,
        "fee": settings.bank_transfer_fee,
        "to": other.display_name,
        "bank_balance": round(character.bank_balance, 2),
    }


async def take_loan(db: AsyncSession, character: Character, amount: float) -> Loan:
    ensure_can_act(character)
    settings = get_settings()
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if amount > settings.loan_max_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Max loan is ${settings.loan_max_amount:.0f}",
        )

    existing = await db.execute(
        select(Loan).where(
            Loan.character_id == character.id,
            Loan.status == LoanStatus.ACTIVE,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already have an active loan")

    if character.heat >= 25:
        raise HTTPException(status_code=403, detail="Loan denied: heat too high")
    if character.criminal_record_summary:
        raise HTTPException(status_code=403, detail="Loan denied: criminal record")

    now = utcnow()
    total_due = round(amount * (1 + settings.loan_interest_rate), 2)
    loan = Loan(
        character_id=character.id,
        principal=amount,
        remaining=total_due,
        interest_rate=settings.loan_interest_rate,
        status=LoanStatus.ACTIVE,
        issued_at=now,
        due_at=now + timedelta(days=settings.loan_term_real_days),
    )
    # Loans disburse to bank (safer than street cash)
    character.bank_balance = round(character.bank_balance + amount, 2)
    db.add(loan)
    await db.flush()
    await _ledger(
        db, character, BankTxType.LOAN_DISBURSE, amount, note=f"Loan #{loan.id}"
    )
    await db.flush()
    await db.refresh(loan)
    return loan


async def repay_loan(
    db: AsyncSession, character: Character, loan_id: int, amount: float
) -> Loan:
    ensure_can_act(character)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    loan = await db.get(Loan, loan_id)
    if loan is None or loan.character_id != character.id:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status != LoanStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Loan is not active")

    # Prefer bank, then cash
    pay = min(amount, loan.remaining)
    from_bank = min(pay, character.bank_balance)
    from_cash = pay - from_bank
    if from_cash > character.cash:
        raise HTTPException(status_code=400, detail="Insufficient funds (bank + cash)")

    character.bank_balance = round(character.bank_balance - from_bank, 2)
    character.cash = round(character.cash - from_cash, 2)
    loan.remaining = round(loan.remaining - pay, 2)
    loan.payments_made += 1
    if loan.remaining <= 0.009:
        loan.remaining = 0.0
        loan.status = LoanStatus.PAID

    await _ledger(
        db, character, BankTxType.LOAN_REPAY, pay, note=f"Loan #{loan.id} repayment"
    )
    await db.flush()
    await db.refresh(loan)
    return loan


async def list_loans(db: AsyncSession, character_id: int) -> list[Loan]:
    result = await db.execute(
        select(Loan).where(Loan.character_id == character_id).order_by(Loan.id.desc())
    )
    return list(result.scalars().all())


async def list_transactions(
    db: AsyncSession, character_id: int, *, limit: int = 50
) -> list[BankTransaction]:
    result = await db.execute(
        select(BankTransaction)
        .where(BankTransaction.character_id == character_id)
        .order_by(BankTransaction.id.desc())
        .limit(min(limit, 100))
    )
    return list(result.scalars().all())


async def mark_overdue_defaults(db: AsyncSession, character: Character) -> None:
    now = utcnow()
    result = await db.execute(
        select(Loan).where(
            Loan.character_id == character.id,
            Loan.status == LoanStatus.ACTIVE,
            Loan.due_at < now,
        )
    )
    for loan in result.scalars().all():
        loan.status = LoanStatus.DEFAULTED
        character.reputation = max(-100, character.reputation - 15)
        character.heat = min(100.0, character.heat + 10)
    await db.flush()


async def bank_summary(db: AsyncSession, character: Character) -> dict:
    await apply_savings_interest(db, character)
    await mark_overdue_defaults(db, character)
    settings = get_settings()
    loans = await list_loans(db, character.id)
    return {
        "cash": round(character.cash, 2),
        "bank_balance": round(character.bank_balance, 2),
        "savings_apr": settings.savings_apr,
        "transfer_fee": settings.bank_transfer_fee,
        "loans": loans,
    }
