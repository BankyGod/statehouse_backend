from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.legislation import BillVoteChoice
from app.models.user import User
from app.services import character_service, legislation_service
from pydantic import BaseModel, Field

router = APIRouter(prefix="/legislation", tags=["legislation"])


class ProposeBillRequest(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    summary: str = Field(min_length=10, max_length=2000)


class VoteChoiceRequest(BaseModel):
    choice: str = Field(pattern="^(yes|no|abstain)$")


@router.get("/bills")
async def bills(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    await legislation_service.resolve_due_bills(db)
    items = await legislation_service.list_bills(db, status=status)
    return [
        {
            "id": b.id,
            "title": b.title,
            "summary": b.summary,
            "sponsor_character_id": b.sponsor_character_id,
            "sponsor_state_id": b.sponsor_state_id,
            "status": b.status.value,
            "yes_votes": b.yes_votes,
            "no_votes": b.no_votes,
            "abstain_votes": b.abstain_votes,
            "npc_yes": b.npc_yes,
            "npc_no": b.npc_no,
            "debate_ends_at": b.debate_ends_at,
            "vetoed": b.vetoed,
            "enacted_at": b.enacted_at,
        }
        for b in items
    ]


@router.post("/bills", status_code=201)
async def propose(
    payload: ProposeBillRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    bill = await legislation_service.propose_bill(
        db, character, payload.title, payload.summary
    )
    return {
        "id": bill.id,
        "title": bill.title,
        "status": bill.status.value,
        "debate_ends_at": bill.debate_ends_at,
    }


@router.post("/bills/{bill_id}/vote")
async def vote_bill(
    bill_id: int,
    payload: VoteChoiceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await legislation_service.vote_on_bill(
        db, character, bill_id, BillVoteChoice(payload.choice)
    )


@router.post("/bills/{bill_id}/veto")
async def veto(
    bill_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    bill = await legislation_service.veto_bill(db, character, bill_id)
    return {"id": bill.id, "status": bill.status.value, "vetoed": bill.vetoed}


@router.get("/budget/current")
async def current_budget(db: AsyncSession = Depends(get_db)):
    budget = await legislation_service.get_current_budget(db)
    if budget is None:
        return {"budget": None}
    return {
        "budget": {
            "id": budget.id,
            "title": budget.title,
            "summary": budget.summary,
            "national_tax_rate": budget.national_tax_rate,
            "status": budget.status.value,
            "yes_votes": budget.yes_votes,
            "no_votes": budget.no_votes,
            "opens_at": budget.opens_at,
            "closes_at": budget.closes_at,
        }
    }


@router.post("/budget/{budget_id}/vote")
async def vote_budget(
    budget_id: int,
    payload: VoteChoiceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    choice = BillVoteChoice(payload.choice)
    return await legislation_service.vote_on_budget(db, character, budget_id, choice)
