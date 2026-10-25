from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import (
    BankAmountRequest,
    BankMoveOut,
    BankSummaryOut,
    BankTransferRequest,
    BankTxOut,
    LoanCreateRequest,
    LoanOut,
    LoanRepayRequest,
)
from app.services import bank_service, character_service

router = APIRouter(prefix="/bank", tags=["bank"])


@router.get("/me", response_model=BankSummaryOut)
async def bank_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    summary = await bank_service.bank_summary(db, character)
    return BankSummaryOut(
        cash=summary["cash"],
        bank_balance=summary["bank_balance"],
        savings_apr=summary["savings_apr"],
        transfer_fee=summary["transfer_fee"],
        loans=summary["loans"],
    )


@router.get("/transactions", response_model=list[BankTxOut])
async def transactions(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    rows = await bank_service.list_transactions(db, character.id, limit=limit)
    return [
        BankTxOut(
            id=t.id,
            tx_type=t.tx_type.value,
            amount=t.amount,
            balance_after=t.balance_after,
            counterparty_id=t.counterparty_id,
            note=t.note,
            posted_at=t.posted_at,
        )
        for t in rows
    ]


@router.post("/deposit", response_model=BankMoveOut)
async def deposit(
    payload: BankAmountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await bank_service.deposit(db, character, payload.amount)


@router.post("/withdraw", response_model=BankMoveOut)
async def withdraw(
    payload: BankAmountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await bank_service.withdraw(db, character, payload.amount)


@router.post("/transfer")
async def transfer(
    payload: BankTransferRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await bank_service.transfer(
        db, character, payload.to_display_name, payload.amount
    )


@router.post("/loans", response_model=LoanOut, status_code=201)
async def create_loan(
    payload: LoanCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await bank_service.take_loan(db, character, payload.amount)


@router.post("/loans/{loan_id}/repay", response_model=LoanOut)
async def repay_loan(
    loan_id: int,
    payload: LoanRepayRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await bank_service.repay_loan(db, character, loan_id, payload.amount)
