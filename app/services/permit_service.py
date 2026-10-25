from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.character import Character
from app.models.permit import Permit, PermitStatus, PermitType
from app.models.state import State
from app.services.character_service import ensure_can_act

BASE_FEES = {
    PermitType.WORK: 75.0,
    PermitType.BUSINESS: 200.0,
    PermitType.TRAVEL: 25.0,
}

VALIDITY_DAYS = {
    PermitType.WORK: 14,
    PermitType.BUSINESS: 30,
    PermitType.TRAVEL: 7,
}


async def apply_permit(
    db: AsyncSession,
    character: Character,
    state_id: int,
    permit_type: PermitType,
) -> Permit:
    ensure_can_act(character)

    if state_id == character.home_state_id and permit_type in (
        PermitType.WORK,
        PermitType.TRAVEL,
    ):
        raise HTTPException(
            status_code=400,
            detail="No permit needed for work/travel in your home state",
        )

    state = await db.get(State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    # Tight security: high heat → denial
    if character.heat >= 40:
        raise HTTPException(
            status_code=403,
            detail="Permit denied: security flag (heat too high)",
        )
    if character.criminal_record_summary and permit_type == PermitType.BUSINESS:
        raise HTTPException(
            status_code=403,
            detail="Business permit denied: criminal record on file",
        )

    fee = BASE_FEES[permit_type] * state.permit_fee_multiplier
    if character.cash < fee:
        raise HTTPException(status_code=400, detail="Insufficient funds for permit fee")

    # Expire older active permits of same type/state
    existing = await db.execute(
        select(Permit).where(
            Permit.character_id == character.id,
            Permit.state_id == state_id,
            Permit.permit_type == permit_type,
            Permit.status == PermitStatus.ACTIVE,
        )
    )
    for old in existing.scalars().all():
        old.status = PermitStatus.EXPIRED

    now = utcnow()
    character.cash -= fee
    permit = Permit(
        character_id=character.id,
        state_id=state_id,
        permit_type=permit_type,
        status=PermitStatus.ACTIVE,
        fee_paid=fee,
        issued_at=now,
        expires_at=now + timedelta(days=VALIDITY_DAYS[permit_type]),
        notes="Auto-approved by labour office",
    )
    db.add(permit)
    await db.flush()
    await db.refresh(permit)
    return permit


async def list_permits(db: AsyncSession, character_id: int) -> list[Permit]:
    result = await db.execute(
        select(Permit).where(Permit.character_id == character_id)
    )
    return list(result.scalars().all())
