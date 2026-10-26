from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import character_service, treasury_service

router = APIRouter(prefix="/treasury", tags=["treasury"])


class DisburseRequest(BaseModel):
    amount: float = Field(gt=0)
    reason: str = Field(min_length=8, max_length=255)
    to_character_id: int | None = None
    to_display_name: str | None = None


class DonateRequest(BaseModel):
    amount: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=255)


@router.get("")
async def get_treasury(
    limit: int = Query(40, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """National treasury — visible to President, VP, Speaker, MPs, and ministers."""
    character = await character_service.get_character_for_user(db, user)
    return await treasury_service.treasury_snapshot(db, character, limit=limit)


@router.get("/my-rate")
async def my_tax_rate(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Any citizen can see their own tax rates (not the treasury balance)."""
    character = await character_service.get_character_for_user(db, user)
    rate = await treasury_service.get_tax_rate(db, character)
    corp = await treasury_service.get_corporate_tax_rate(db)
    nation = await treasury_service.get_nation(db)
    access = await treasury_service.office_roles(db, character)
    return {
        "income_tax_rate": rate,
        "corporate_tax_rate": corp,
        "national_tax_rate": float(nation.national_tax_rate or 0.05),
        "can_view_treasury": access["can_view"],
        "can_spend_treasury": access["can_spend"],
    }


@router.post("/disburse")
async def disburse(
    payload: DisburseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """President or Finance Minister only — pay a recipient from the treasury."""
    character = await character_service.get_character_for_user(db, user)
    result = await treasury_service.disburse(
        db,
        character,
        amount=payload.amount,
        reason=payload.reason,
        to_character_id=payload.to_character_id,
        to_display_name=payload.to_display_name,
    )
    await db.commit()
    return result


@router.post("/donate")
async def donate(
    payload: DonateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """President or Finance Minister may add personal cash into the treasury."""
    character = await character_service.get_character_for_user(db, user)
    result = await treasury_service.donate(
        db, character, amount=payload.amount, note=payload.note
    )
    await db.commit()
    return result
