from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.character import Character
from app.models.party import PartyIdeology, PartyMembership, PoliticalParty
from app.services.character_service import ensure_can_act

PARTY_SEED = [
    {
        "name": "United Progress Alliance",
        "short_name": "UPA",
        "slogan": "Jobs, schools, and a fair wage for every state.",
        "ideology": PartyIdeology.LABOUR,
        "description": "Centre-left party focused on workers, housing, and public services.",
        "color_hex": "#1d4ed8",
        "npc_leader_name": "Chairperson Ama Boateng (NPC)",
        "npc_member_count": 4200,
    },
    {
        "name": "National Prosperity Party",
        "short_name": "NPP",
        "slogan": "Enterprise builds the nation.",
        "ideology": PartyIdeology.BUSINESS,
        "description": "Pro-business party favouring trade, low taxes, and private growth.",
        "color_hex": "#b45309",
        "npc_leader_name": "Chairperson Daniel Okoro (NPC)",
        "npc_member_count": 3900,
    },
    {
        "name": "Amir People's Unity",
        "short_name": "APU",
        "slogan": "One nation, many homes — security first.",
        "ideology": PartyIdeology.NATIONALIST,
        "description": "National-unity party emphasising security, borders, and tradition.",
        "color_hex": "#991b1b",
        "npc_leader_name": "Chairperson Ibrahim Yusuf (NPC)",
        "npc_member_count": 3100,
    },
    {
        "name": "Green Horizon Movement",
        "short_name": "GHM",
        "slogan": "Clean land, clean future.",
        "ideology": PartyIdeology.GREEN,
        "description": "Environment-first party for farming reform and renewable energy.",
        "color_hex": "#15803d",
        "npc_leader_name": "Chairperson Efua Darko (NPC)",
        "npc_member_count": 1800,
    },
    {
        "name": "Civic Centre Party",
        "short_name": "CCP",
        "slogan": "Steady hands for United Amir.",
        "ideology": PartyIdeology.CENTRIST,
        "description": "Moderate caretaker party; currently the NPC governing coalition core.",
        "color_hex": "#475569",
        "npc_leader_name": "Chairperson Kwesi Nkrumah (NPC)",
        "npc_member_count": 5100,
    },
]


async def ensure_parties_seeded(db: AsyncSession) -> int:
    result = await db.execute(select(PoliticalParty.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0
    for data in PARTY_SEED:
        db.add(PoliticalParty(**data, member_count=0, is_npc_led=True))
    await db.flush()
    return len(PARTY_SEED)


async def list_parties(db: AsyncSession) -> list[dict]:
    await ensure_parties_seeded(db)
    result = await db.execute(select(PoliticalParty).order_by(PoliticalParty.id))
    out = []
    for p in result.scalars().all():
        leader = p.npc_leader_name
        if p.leader_character_id:
            ch = await db.get(Character, p.leader_character_id)
            if ch:
                leader = ch.display_name
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "short_name": p.short_name,
                "slogan": p.slogan,
                "ideology": p.ideology.value,
                "description": p.description,
                "color_hex": p.color_hex,
                "leader": leader,
                "is_npc_led": p.is_npc_led,
                "player_members": p.member_count,
                "npc_members": p.npc_member_count,
                "total_members": p.member_count + p.npc_member_count,
            }
        )
    return out


async def my_membership(db: AsyncSession, character_id: int) -> dict | None:
    result = await db.execute(
        select(PartyMembership).where(PartyMembership.character_id == character_id)
    )
    mem = result.scalar_one_or_none()
    if mem is None:
        return None
    party = await db.get(PoliticalParty, mem.party_id)
    return {
        "party_id": mem.party_id,
        "party_name": party.name if party else None,
        "short_name": party.short_name if party else None,
        "rank": mem.rank,
        "joined_at": mem.joined_at,
    }


async def join_party(
    db: AsyncSession, character: Character, party_id: int
) -> dict:
    ensure_can_act(character)
    await ensure_parties_seeded(db)
    party = await db.get(PoliticalParty, party_id)
    if party is None:
        raise HTTPException(status_code=404, detail="Party not found")

    existing = await db.execute(
        select(PartyMembership).where(PartyMembership.character_id == character.id)
    )
    mem = existing.scalar_one_or_none()
    if mem and mem.party_id == party_id:
        return await my_membership(db, character.id)  # type: ignore
    if mem:
        old = await db.get(PoliticalParty, mem.party_id)
        if old:
            old.member_count = max(0, old.member_count - 1)
        await db.delete(mem)
        await db.flush()

    db.add(
        PartyMembership(
            party_id=party.id,
            character_id=character.id,
            rank="member",
            joined_at=utcnow(),
        )
    )
    party.member_count += 1
    character.reputation = min(100, character.reputation + 2)
    await db.flush()
    return await my_membership(db, character.id)  # type: ignore


async def leave_party(db: AsyncSession, character: Character) -> dict:
    ensure_can_act(character)
    result = await db.execute(
        select(PartyMembership).where(PartyMembership.character_id == character.id)
    )
    mem = result.scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=400, detail="Not in a party")
    party = await db.get(PoliticalParty, mem.party_id)
    if party:
        party.member_count = max(0, party.member_count - 1)
        if party.leader_character_id == character.id:
            party.leader_character_id = None
            party.is_npc_led = True
    await db.delete(mem)
    await db.flush()
    return {"left": True, "party_id": party.id if party else None}
