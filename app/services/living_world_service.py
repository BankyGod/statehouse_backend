"""Keep United Amir feeling populated with NPC office-holders."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.state import State
from app.services import (
    cabinet_service,
    government_service,
    party_service,
    politics_service,
)

DEFAULT_PRESIDENT = "President Ama Serwaa (NPC)"
DEFAULT_VP = "Vice President Kwesi Nkrumah (NPC)"
DEFAULT_SPEAKER = "Speaker Ruth Mensah (NPC)"


async def ensure_living_government(db: AsyncSession) -> dict:
    """Idempotent: NPC president/VP/speaker, cabinet, parties, civil posts, MPs."""
    nation = await politics_service.get_or_create_nation(db)

    if not nation.president_character_id:
        nation.president_npc_name = nation.president_npc_name or DEFAULT_PRESIDENT
    if not getattr(nation, "vice_president_character_id", None):
        if not getattr(nation, "vice_president_npc_name", None):
            nation.vice_president_npc_name = DEFAULT_VP
    if not nation.speaker_character_id:
        if not getattr(nation, "speaker_npc_name", None):
            nation.speaker_npc_name = DEFAULT_SPEAKER

    # Ensure every state has an NPC MP name when no player MP
    states = list((await db.execute(select(State))).scalars().all())
    mp_fixed = 0
    for state in states:
        if not state.mp_character_id and not state.npc_mp_name:
            state.npc_mp_name = f"Hon. Caretaker MP - {state.name} (NPC)"
            mp_fixed += 1

    cabinet = await cabinet_service.ensure_cabinet_seeded(db)
    # If cabinet exists but somehow empty seats, re-seed missing portfolios
    from app.models.cabinet import CabinetSeat, PORTFOLIO_LABELS, Portfolio
    from app.core.game_time import utcnow

    existing = {
        s.portfolio
        for s in (
            await db.execute(select(CabinetSeat))
        ).scalars().all()
    }
    cab_added = 0
    now = utcnow()
    for portfolio, npc in cabinet_service.NPC_MINISTERS.items():
        if portfolio not in existing:
            db.add(
                CabinetSeat(
                    portfolio=portfolio,
                    title=PORTFOLIO_LABELS[portfolio],
                    character_id=None,
                    npc_name=npc,
                    is_npc=True,
                    appointed_at=now,
                    last_salary_at=now,
                )
            )
            cab_added += 1

    parties = await party_service.ensure_parties_seeded(db)
    posts = await government_service.ensure_government_posts(db)
    await db.flush()
    return {
        "president_npc": nation.president_npc_name,
        "vice_president_npc": getattr(nation, "vice_president_npc_name", DEFAULT_VP),
        "speaker_npc": getattr(nation, "speaker_npc_name", DEFAULT_SPEAKER),
        "cabinet_seeded": cabinet,
        "cabinet_added": cab_added,
        "mp_names_fixed": mp_fixed,
        "parties": parties,
        "government_posts": posts,
        "states": len(states),
    }
