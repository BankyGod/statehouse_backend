from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.models.politics import (
    Ballot,
    Candidacy,
    Election,
    ElectionStatus,
    NationOffice,
    RaceType,
)
from app.models.state import State
from app.services.character_service import ensure_can_act


async def get_or_create_nation(db: AsyncSession) -> NationOffice:
    nation = await db.get(NationOffice, 1)
    if nation is None:
        nation = NationOffice(
            id=1,
            president_npc_name="President Ama Serwaa (NPC)",
            vice_president_npc_name="Vice President Kwesi Nkrumah (NPC)",
            speaker_npc_name="Speaker Ruth Mensah (NPC)",
        )
        db.add(nation)
        await db.flush()
        return nation
    # Backfill NPC labels if columns were added later
    if not nation.president_character_id and not nation.president_npc_name:
        nation.president_npc_name = "President Ama Serwaa (NPC)"
    if not getattr(nation, "vice_president_character_id", None) and not getattr(
        nation, "vice_president_npc_name", None
    ):
        nation.vice_president_npc_name = "Vice President Kwesi Nkrumah (NPC)"
    if not nation.speaker_character_id and not getattr(
        nation, "speaker_npc_name", None
    ):
        nation.speaker_npc_name = "Speaker Ruth Mensah (NPC)"
    return nation


async def get_current_election(db: AsyncSession) -> Election | None:
    result = await db.execute(
        select(Election)
        .where(Election.status != ElectionStatus.CLOSED)
        .order_by(Election.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def advance_election_phases(db: AsyncSession) -> Election | None:
    """Move campaign→voting→resolve when timers elapse."""
    election = await get_current_election(db)
    if election is None:
        return None

    now = utcnow()

    def _aware(dt):
        if dt is not None and dt.tzinfo is None:
            from datetime import timezone

            return dt.replace(tzinfo=timezone.utc)
        return dt

    voting_starts = _aware(election.voting_starts_at)
    voting_ends = _aware(election.voting_ends_at)

    if election.status == ElectionStatus.UPCOMING and _aware(election.campaign_starts_at) <= now:
        election.status = ElectionStatus.CAMPAIGN
    if election.status == ElectionStatus.CAMPAIGN and voting_starts <= now:
        election.status = ElectionStatus.VOTING
    if election.status == ElectionStatus.VOTING and voting_ends <= now:
        await resolve_election(db, election)

    await db.flush()
    return election


async def parliament(db: AsyncSession) -> dict:
    nation = await get_or_create_nation(db)
    result = await db.execute(select(State).order_by(State.name))
    seats = []
    for state in result.scalars().all():
        mp_name = state.npc_mp_name
        is_npc = True
        if state.mp_character_id:
            mp = await db.get(Character, state.mp_character_id)
            if mp:
                mp_name = mp.display_name
                is_npc = False
        seats.append(
            {
                "state_id": state.id,
                "state_name": state.name,
                "state_slug": state.slug,
                "mp_name": mp_name,
                "mp_character_id": state.mp_character_id,
                "is_npc": is_npc,
            }
        )

    president_name = nation.president_npc_name
    president_is_npc = True
    if nation.president_character_id:
        prez = await db.get(Character, nation.president_character_id)
        if prez:
            president_name = prez.display_name
            president_is_npc = False

    vp_name = getattr(nation, "vice_president_npc_name", None) or "Vice President (NPC)"
    vp_is_npc = True
    vp_id = getattr(nation, "vice_president_character_id", None)
    if vp_id:
        vp = await db.get(Character, vp_id)
        if vp:
            vp_name = vp.display_name
            vp_is_npc = False

    speaker_name = getattr(nation, "speaker_npc_name", None) or "Speaker (NPC)"
    speaker_is_npc = True
    if nation.speaker_character_id:
        sp = await db.get(Character, nation.speaker_character_id)
        if sp:
            speaker_name = sp.display_name
            speaker_is_npc = False

    from app.services import office_pay_service

    return {
        "seats": seats,
        "majority_needed": 11,
        "veto_override_needed": 14,
        "president": {
            "name": president_name,
            "character_id": nation.president_character_id,
            "is_npc": president_is_npc,
        },
        "vice_president": {
            "name": vp_name,
            "character_id": vp_id,
            "is_npc": vp_is_npc,
        },
        "speaker": {
            "name": speaker_name,
            "character_id": nation.speaker_character_id,
            "is_npc": speaker_is_npc,
        },
        "office_pay": office_pay_service.office_pay_catalog(),
    }


def _check_eligible(character: Character, race: RaceType) -> None:
    settings = get_settings()
    if character.heat >= settings.max_heat_to_run:
        raise HTTPException(status_code=403, detail="Heat too high to run for office")
    if character.criminal_record_summary and race == RaceType.PRESIDENT:
        raise HTTPException(
            status_code=403, detail="Criminal record blocks presidential run"
        )
    if race == RaceType.MP and character.age_years < settings.mp_min_age:
        raise HTTPException(
            status_code=400,
            detail=f"Must be at least {settings.mp_min_age:.0f} to run for MP",
        )
    if race == RaceType.PRESIDENT and character.age_years < settings.president_min_age:
        raise HTTPException(
            status_code=400,
            detail=f"Must be at least {settings.president_min_age:.0f} to run for president",
        )


async def register_candidacy(
    db: AsyncSession,
    character: Character,
    election_id: int,
    race_type: RaceType,
    slogan: str,
) -> Candidacy:
    ensure_can_act(character)
    election = await db.get(Election, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found")
    if election.status not in (ElectionStatus.CAMPAIGN, ElectionStatus.VOTING):
        raise HTTPException(status_code=400, detail="Not open for candidacy")

    _check_eligible(character, race_type)
    settings = get_settings()
    fee = (
        settings.candidacy_fee_president
        if race_type == RaceType.PRESIDENT
        else settings.candidacy_fee_mp
    )
    if character.cash < fee:
        raise HTTPException(status_code=400, detail=f"Candidacy fee is ${fee:.0f}")

    existing = await db.execute(
        select(Candidacy).where(
            Candidacy.election_id == election_id,
            Candidacy.character_id == character.id,
            Candidacy.race_type == race_type,
            Candidacy.withdrawn.is_(False),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already a candidate in this race")

    state_id = character.home_state_id if race_type == RaceType.MP else None
    character.cash -= fee
    from app.services import treasury_service

    await treasury_service.collect_fee(
        db,
        fee,
        note=f"Candidacy fee — {race_type.value}",
        character_id=character.id,
    )
    candidacy = Candidacy(
        election_id=election_id,
        character_id=character.id,
        race_type=race_type,
        state_id=state_id,
        slogan=slogan.strip()[:160] or "For United Amir",
        vote_count=0,
    )
    db.add(candidacy)
    await db.flush()
    await db.refresh(candidacy)
    return candidacy


async def list_candidates(
    db: AsyncSession,
    election_id: int,
    *,
    race_type: RaceType | None = None,
    state_id: int | None = None,
) -> list[dict]:
    stmt = select(Candidacy).where(
        Candidacy.election_id == election_id,
        Candidacy.withdrawn.is_(False),
    )
    if race_type:
        stmt = stmt.where(Candidacy.race_type == race_type)
    if state_id is not None:
        stmt = stmt.where(Candidacy.state_id == state_id)
    result = await db.execute(stmt.order_by(Candidacy.vote_count.desc()))
    out = []
    for c in result.scalars().all():
        ch = await db.get(Character, c.character_id)
        out.append(
            {
                "id": c.id,
                "election_id": c.election_id,
                "character_id": c.character_id,
                "display_name": ch.display_name if ch else "Unknown",
                "race_type": c.race_type.value,
                "state_id": c.state_id,
                "slogan": c.slogan,
                "vote_count": c.vote_count,
                "is_winner": c.is_winner,
            }
        )
    return out


async def cast_vote(
    db: AsyncSession, character: Character, election_id: int, candidacy_id: int
) -> dict:
    ensure_can_act(character)
    election = await db.get(Election, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found")
    if election.status != ElectionStatus.VOTING:
        raise HTTPException(status_code=400, detail="Voting is not open")

    candidacy = await db.get(Candidacy, candidacy_id)
    if (
        candidacy is None
        or candidacy.election_id != election_id
        or candidacy.withdrawn
    ):
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidacy.race_type == RaceType.MP:
        if candidacy.state_id != character.home_state_id:
            raise HTTPException(
                status_code=403,
                detail="You may only vote for an MP candidate in your home state",
            )

    prior = await db.execute(
        select(Ballot).where(
            Ballot.election_id == election_id,
            Ballot.voter_id == character.id,
            Ballot.race_type == candidacy.race_type,
        )
    )
    if prior.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Already voted in this race for this election"
        )

    ballot = Ballot(
        election_id=election_id,
        voter_id=character.id,
        race_type=candidacy.race_type,
        candidacy_id=candidacy.id,
        state_id=character.home_state_id
        if candidacy.race_type == RaceType.MP
        else None,
    )
    candidacy.vote_count += 1
    db.add(ballot)
    await db.flush()
    return {
        "election_id": election_id,
        "candidacy_id": candidacy_id,
        "race_type": candidacy.race_type.value,
        "message": "Vote recorded",
    }


async def resolve_election(db: AsyncSession, election: Election) -> dict:
    if election.status == ElectionStatus.CLOSED:
        return {"message": "Already resolved"}

    # MP seats
    states = (await db.execute(select(State))).scalars().all()
    mp_results = []
    for state in states:
        result = await db.execute(
            select(Candidacy).where(
                Candidacy.election_id == election.id,
                Candidacy.race_type == RaceType.MP,
                Candidacy.state_id == state.id,
                Candidacy.withdrawn.is_(False),
            )
        )
        candidates = list(result.scalars().all())
        if not candidates:
            mp_results.append(
                {"state_id": state.id, "winner": state.npc_mp_name, "npc": True}
            )
            continue
        winner = max(candidates, key=lambda c: c.vote_count)
        for c in candidates:
            c.is_winner = c.id == winner.id
        state.mp_character_id = winner.character_id
        ch = await db.get(Character, winner.character_id)
        if ch:
            ch.reputation += 20
            from app.services import office_pay_service

            await office_pay_service.end_employee_jobs_for_office(
                db, ch, reason="Elected to Parliament — employee jobs ended"
            )
        mp_results.append(
            {
                "state_id": state.id,
                "winner": ch.display_name if ch else str(winner.character_id),
                "winner_character_id": winner.character_id,
                "votes": winner.vote_count,
                "npc": False,
            }
        )

    # President
    nation = await get_or_create_nation(db)
    prez_result = await db.execute(
        select(Candidacy).where(
            Candidacy.election_id == election.id,
            Candidacy.race_type == RaceType.PRESIDENT,
            Candidacy.withdrawn.is_(False),
        )
    )
    prez_candidates = list(prez_result.scalars().all())
    president_info: dict
    if prez_candidates:
        winner = max(prez_candidates, key=lambda c: c.vote_count)
        for c in prez_candidates:
            c.is_winner = c.id == winner.id
        nation.president_character_id = winner.character_id
        ch = await db.get(Character, winner.character_id)
        if ch:
            ch.reputation += 50
            from app.services import office_pay_service

            await office_pay_service.end_employee_jobs_for_office(
                db, ch, reason="Elected President — employee jobs ended"
            )
        president_info = {
            "winner": ch.display_name if ch else str(winner.character_id),
            "winner_character_id": winner.character_id,
            "votes": winner.vote_count,
            "npc": False,
        }
    else:
        president_info = {"winner": nation.president_npc_name, "npc": True}

    election.status = ElectionStatus.CLOSED
    election.resolved_at = utcnow()
    from app.services import news_service, office_pay_service

    await office_pay_service.pay_election_win_bonuses(
        db,
        president_character_id=president_info.get("winner_character_id"),
        mp_character_ids=[
            r["winner_character_id"]
            for r in mp_results
            if not r.get("npc") and r.get("winner_character_id")
        ],
    )

    await news_service.publish(
        db,
        f"Election results: {election.title}",
        f"President: {president_info.get('winner')}. "
        f"Player MP seats won: {sum(1 for r in mp_results if not r.get('npc'))}.",
        category="politics",
    )
    await db.flush()
    return {"mp_results": mp_results, "president": president_info}


async def create_election_cycle(db: AsyncSession, *, force_voting: bool = False) -> Election:
    settings = get_settings()
    now = utcnow()
    if force_voting:
        campaign_start = now - timedelta(days=1)
        voting_start = now
        voting_end = now + timedelta(days=settings.election_voting_days)
    else:
        campaign_start = now
        voting_start = now + timedelta(days=settings.election_campaign_days)
        voting_end = voting_start + timedelta(days=settings.election_voting_days)
    term_end = voting_end + timedelta(days=settings.election_term_days)

    election = Election(
        title=f"General Election {now.year}",
        status=ElectionStatus.VOTING if force_voting else ElectionStatus.CAMPAIGN,
        campaign_starts_at=campaign_start,
        voting_starts_at=voting_start,
        voting_ends_at=voting_end,
        term_ends_at=term_end,
    )
    db.add(election)
    await get_or_create_nation(db)
    await db.flush()
    await db.refresh(election)
    return election
