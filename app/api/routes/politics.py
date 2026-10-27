from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.politics import RaceType
from app.models.user import User
from app.schemas.life import CandidacyRegisterRequest, VoteRequest
from app.services import character_service, politics_service

router = APIRouter(prefix="/politics", tags=["politics"])


@router.get("/parliament")
async def get_parliament(db: AsyncSession = Depends(get_db)):
    return await politics_service.parliament(db)


@router.get("/office-pay")
async def office_pay_catalog():
    from app.services import office_pay_service

    return office_pay_service.office_pay_catalog()


@router.get("/office-pay/me")
async def my_office_pay(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import office_pay_service

    character = await character_service.get_character_for_user(db, user)
    return await office_pay_service.my_office_pay(db, character)


@router.get("/elections/current")
async def current_election(db: AsyncSession = Depends(get_db)):
    await politics_service.advance_election_phases(db)
    election = await politics_service.get_current_election(db)
    if election is None:
        return {"election": None}
    return {
        "election": {
            "id": election.id,
            "title": election.title,
            "status": election.status.value,
            "campaign_starts_at": election.campaign_starts_at,
            "voting_starts_at": election.voting_starts_at,
            "voting_ends_at": election.voting_ends_at,
            "term_ends_at": election.term_ends_at,
            "resolved_at": election.resolved_at,
        }
    }


@router.get("/elections/{election_id}/candidates")
async def candidates(
    election_id: int,
    race_type: str | None = Query(default=None),
    state_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    race = RaceType(race_type) if race_type else None
    return await politics_service.list_candidates(
        db, election_id, race_type=race, state_id=state_id
    )


@router.post("/elections/{election_id}/run", status_code=201)
async def run_for_office(
    election_id: int,
    payload: CandidacyRegisterRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await politics_service.register_candidacy(
        db,
        character,
        election_id,
        RaceType(payload.race_type),
        payload.slogan,
    )


@router.post("/elections/{election_id}/vote")
async def vote(
    election_id: int,
    payload: VoteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await politics_service.cast_vote(
        db, character, election_id, payload.candidacy_id
    )


@router.post("/elections/{election_id}/resolve")
async def resolve(
    election_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close voting early / resolve tallies (useful for admin & testing)."""
    election = await politics_service.get_current_election(db)
    if election is None or election.id != election_id:
        from fastapi import HTTPException

        # Allow resolving specific closed-check
        from app.models.politics import Election

        election = await db.get(Election, election_id)
        if election is None:
            raise HTTPException(status_code=404, detail="Election not found")
    return await politics_service.resolve_election(db, election)
