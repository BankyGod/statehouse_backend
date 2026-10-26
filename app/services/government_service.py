"""Civil service posts — NPC-staffed until players take them."""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.character import Character
from app.models.government import GovPostTier, GovernmentPost
from app.models.state import State
from app.services.character_service import ensure_can_act
from app.services.education_service import get_highest_education_level
from app.services import notify_service

# National + state civil service template
GOV_POST_TEMPLATES: list[dict] = [
    # National executive agencies (Amira Central flavour, state_id null = national)
    {
        "title": "Treasury Analyst",
        "agency": "Ministry of Finance",
        "portfolio": "finance",
        "tier": GovPostTier.OFFICER,
        "description": "Prepare budget briefs and tax forecasts for the ministry.",
        "wage_per_week": 280.0,
        "min_education_level": 3,
        "min_reputation": 5,
        "npc_name": "NPC: Selorm Addae",
    },
    {
        "title": "Customs Officer",
        "agency": "Border & Revenue Service",
        "portfolio": "interior",
        "tier": GovPostTier.OFFICER,
        "description": "Inspect cargo and collect duties at major entry points.",
        "wage_per_week": 260.0,
        "min_education_level": 2,
        "min_reputation": 0,
        "npc_name": "NPC: Fatima Diallo",
    },
    {
        "title": "Public Health Inspector",
        "agency": "Ministry of Health",
        "portfolio": "health",
        "tier": GovPostTier.OFFICER,
        "description": "Audit clinics and market hygiene standards.",
        "wage_per_week": 250.0,
        "min_education_level": 2,
        "min_reputation": 0,
        "npc_name": "NPC: Dr. Helen Quaye",
    },
    {
        "title": "Curriculum Officer",
        "agency": "Ministry of Education",
        "portfolio": "education",
        "tier": GovPostTier.SENIOR,
        "description": "Approve school materials and exam schedules.",
        "wage_per_week": 310.0,
        "min_education_level": 3,
        "min_reputation": 10,
        "npc_name": "NPC: Yaw Owusu",
    },
    {
        "title": "Defence Logistics Clerk",
        "agency": "Ministry of Defence",
        "portfolio": "defence",
        "tier": GovPostTier.JUNIOR,
        "description": "Track supply requests for barracks and border posts.",
        "wage_per_week": 220.0,
        "min_education_level": 1,
        "min_reputation": 0,
        "npc_name": "NPC: Patrick Osei",
    },
    {
        "title": "Trade Negotiator Aide",
        "agency": "Ministry of Trade",
        "portfolio": "trade",
        "tier": GovPostTier.SENIOR,
        "description": "Support bilateral trade talks and permit reform.",
        "wage_per_week": 340.0,
        "min_education_level": 3,
        "min_reputation": 15,
        "npc_name": "NPC: Priya Nkrumah",
    },
    {
        "title": "Court Registry Clerk",
        "agency": "Ministry of Justice",
        "portfolio": "justice",
        "tier": GovPostTier.JUNIOR,
        "description": "File dockets and schedule hearings.",
        "wage_per_week": 210.0,
        "min_education_level": 2,
        "min_reputation": 0,
        "requires_clean_record": True,
        "npc_name": "NPC: Grace Addo",
    },
    {
        "title": "Agricultural Extension Officer",
        "agency": "Ministry of Agriculture",
        "portfolio": "agriculture",
        "tier": GovPostTier.OFFICER,
        "description": "Advise state farms on yields and subsidies.",
        "wage_per_week": 240.0,
        "min_education_level": 2,
        "min_reputation": 0,
        "npc_name": "NPC: Ama Serwaa",
    },
    {
        "title": "Energy Grid Technician",
        "agency": "Ministry of Energy",
        "portfolio": "energy",
        "tier": GovPostTier.OFFICER,
        "description": "Maintain national grid monitoring stations.",
        "wage_per_week": 270.0,
        "min_education_level": 2,
        "min_reputation": 0,
        "npc_name": "NPC: Leroy Banks",
    },
    {
        "title": "Rail Operations Supervisor",
        "agency": "Ministry of Transport",
        "portfolio": "transport",
        "tier": GovPostTier.SENIOR,
        "description": "Coordinate freight schedules on the national rail spine.",
        "wage_per_week": 320.0,
        "min_education_level": 2,
        "min_reputation": 8,
        "npc_name": "NPC: Claire Mensah",
    },
    {
        "title": "Director of Civil Service",
        "agency": "Office of the President",
        "portfolio": None,
        "tier": GovPostTier.DIRECTOR,
        "description": "Senior NPC caretaker overseeing hiring across ministries.",
        "wage_per_week": 450.0,
        "min_education_level": 4,
        "min_reputation": 40,
        "npc_name": "NPC: Director Bankole Sarpong",
    },
    {
        "title": "Presidential Press Aide",
        "agency": "Office of the President",
        "portfolio": None,
        "tier": GovPostTier.OFFICER,
        "description": "Draft briefings and statehouse notices.",
        "wage_per_week": 290.0,
        "min_education_level": 3,
        "min_reputation": 10,
        "npc_name": "NPC: Nadia Traore",
    },
]

# One local registry clerk per state (filled by NPC until a player applies)
STATE_POST = {
    "title": "State Registry Clerk",
    "agency": "State Civil Registry",
    "portfolio": "interior",
    "tier": GovPostTier.JUNIOR,
    "description": "Issue local IDs, record births, and process residence paperwork.",
    "wage_per_week": 180.0,
    "min_education_level": 1,
    "min_reputation": 0,
    "requires_clean_record": True,
}

STATE_NPC_NAMES = [
    "NPC: Kofi Adjei",
    "NPC: Ruth Asante",
    "NPC: Samuel Tetteh",
    "NPC: Zainab Yusuf",
    "NPC: Joseph Addai",
    "NPC: Mariam Ba",
    "NPC: Ethan Cole",
    "NPC: Victoria Okeke",
    "NPC: Omar Diallo",
    "NPC: Linda Frimpong",
    "NPC: Jacob Mensah",
    "NPC: Nana Serwaa",
    "NPC: Tunde Bakare",
    "NPC: Elena Frost",
    "NPC: Amina Diallo",
    "NPC: Chris Lambert",
    "NPC: Sofia Mendes",
    "NPC: Raj Patel",
    "NPC: Nora Berg",
    "NPC: Adaeze Nwosu",
]


async def ensure_government_posts(db: AsyncSession) -> int:
    result = await db.execute(select(GovernmentPost.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0

    now = utcnow()
    created = 0
    for tmpl in GOV_POST_TEMPLATES:
        db.add(
            GovernmentPost(
                title=tmpl["title"],
                agency=tmpl["agency"],
                portfolio=tmpl.get("portfolio"),
                state_id=None,
                tier=tmpl["tier"],
                description=tmpl["description"],
                wage_per_week=tmpl["wage_per_week"],
                min_education_level=tmpl["min_education_level"],
                min_reputation=tmpl.get("min_reputation", 0),
                requires_clean_record=tmpl.get("requires_clean_record", True),
                character_id=None,
                npc_name=tmpl["npc_name"],
                is_npc=True,
                hired_at=now,
                last_payday_at=now,
            )
        )
        created += 1

    states = list((await db.execute(select(State).order_by(State.id))).scalars().all())
    for i, state in enumerate(states):
        db.add(
            GovernmentPost(
                title=f"{STATE_POST['title']} - {state.name}",
                agency=STATE_POST["agency"],
                portfolio=STATE_POST["portfolio"],
                state_id=state.id,
                tier=STATE_POST["tier"],
                description=STATE_POST["description"],
                wage_per_week=STATE_POST["wage_per_week"],
                min_education_level=STATE_POST["min_education_level"],
                min_reputation=STATE_POST["min_reputation"],
                requires_clean_record=STATE_POST["requires_clean_record"],
                character_id=None,
                npc_name=STATE_NPC_NAMES[i % len(STATE_NPC_NAMES)],
                is_npc=True,
                hired_at=now,
                last_payday_at=now,
            )
        )
        created += 1

    await db.flush()
    return created


def _post_out(post: GovernmentPost, holder_name: str) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "agency": post.agency,
        "portfolio": post.portfolio,
        "state_id": post.state_id,
        "tier": post.tier.value,
        "description": post.description,
        "wage_per_week": post.wage_per_week,
        "min_education_level": post.min_education_level,
        "min_reputation": post.min_reputation,
        "requires_clean_record": post.requires_clean_record,
        "character_id": post.character_id,
        "holder_name": holder_name,
        "is_npc": post.is_npc,
        "hired_at": post.hired_at,
    }


async def list_posts(
    db: AsyncSession,
    *,
    state_id: int | None = None,
    open_only: bool = False,
) -> list[dict]:
    await ensure_government_posts(db)
    stmt = select(GovernmentPost).order_by(GovernmentPost.id)
    if state_id is not None:
        stmt = stmt.where(
            (GovernmentPost.state_id == state_id) | (GovernmentPost.state_id.is_(None))
        )
    if open_only:
        # "Open" means NPC-held posts players can apply to take over
        stmt = stmt.where(GovernmentPost.is_npc.is_(True))
    result = await db.execute(stmt)
    rows = []
    for post in result.scalars().all():
        name = post.npc_name
        if post.character_id:
            ch = await db.get(Character, post.character_id)
            name = ch.display_name if ch else name
        rows.append(_post_out(post, name))
    return rows


async def my_post(db: AsyncSession, character_id: int) -> dict | None:
    result = await db.execute(
        select(GovernmentPost).where(GovernmentPost.character_id == character_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        return None
    return _post_out(post, "You")


async def apply_for_post(
    db: AsyncSession, character: Character, post_id: int
) -> dict:
    """Take an NPC-held post (or vacant). One government post per player."""
    ensure_can_act(character)
    await ensure_government_posts(db)
    post = await db.get(GovernmentPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Government post not found")
    if not post.is_npc and post.character_id not in (None, character.id):
        raise HTTPException(status_code=400, detail="Post already held by a player")

    held = await my_post(db, character.id)
    if held and held["id"] != post_id:
        raise HTTPException(
            status_code=400,
            detail="Resign your current government post before applying elsewhere",
        )

    edu = await get_highest_education_level(db, character.id)
    if edu < post.min_education_level:
        raise HTTPException(
            status_code=400,
            detail=f"Need education level {post.min_education_level} (you have {edu})",
        )
    if character.reputation < post.min_reputation:
        raise HTTPException(
            status_code=400,
            detail=f"Need reputation {post.min_reputation}",
        )
    if post.requires_clean_record and character.criminal_record_summary:
        raise HTTPException(status_code=400, detail="Clean criminal record required")

    displaced = post.npc_name if post.is_npc else None
    now = utcnow()
    post.character_id = character.id
    post.is_npc = False
    post.hired_at = now
    post.last_payday_at = now
    character.reputation = min(100, character.reputation + 5)
    await notify_service.push(
        db,
        character.id,
        f"Hired: {post.title}",
        body=f"{post.agency} - ${post.wage_per_week:.0f}/week"
        + (f". Replaced {displaced}." if displaced else ""),
        category="government",
    )
    await db.flush()
    return {
        **_post_out(post, character.display_name),
        "displaced_npc": displaced,
        "message": "You joined the civil service. NPC caretaker stepped aside.",
    }


async def resign_post(db: AsyncSession, character: Character) -> dict:
    ensure_can_act(character)
    result = await db.execute(
        select(GovernmentPost).where(GovernmentPost.character_id == character.id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=400, detail="You hold no government post")

    # Restore a generic NPC caretaker
    post.character_id = None
    post.is_npc = True
    if not post.npc_name or not post.npc_name.startswith("NPC:"):
        post.npc_name = f"NPC: Acting {post.title.split(' - ')[0].strip()}"
    post.hired_at = utcnow()
    await db.flush()
    return {"resigned": True, "title": post.title, "npc_caretaker": post.npc_name}


async def pay_gov_salaries(db: AsyncSession) -> int:
    now = utcnow()
    result = await db.execute(
        select(GovernmentPost).where(
            GovernmentPost.is_npc.is_(False),
            GovernmentPost.character_id.is_not(None),
        )
    )
    paid = 0
    for post in result.scalars().all():
        last = post.last_payday_at or post.hired_at or now
        if last.tzinfo is None:
            from datetime import timezone

            last = last.replace(tzinfo=timezone.utc)
        if now < last + timedelta(days=7):
            continue
        ch = await db.get(Character, post.character_id)
        if ch is None:
            continue
        from app.services import treasury_service
        from app.models.treasury import TreasuryTxType

        funded = await treasury_service.debit(
            db,
            post.wage_per_week,
            TreasuryTxType.SALARY,
            note=f"Civil service — {post.title}",
            character_id=ch.id,
            allow_overdraft=True,
        )
        net = 0.0
        tax = 0.0
        if funded > 0:
            pay = await treasury_service.pay_taxable_income(
                db,
                ch,
                funded,
                note=f"Income tax — {post.title}",
            )
            net = pay["net"]
            tax = pay["tax"]
        post.last_payday_at = now
        paid += 1
        tax_bit = f", tax ${tax:.2f}" if tax > 0 else ""
        await notify_service.push(
            db,
            ch.id,
            "Government payday",
            body=f"+${net:.2f} ({post.title}{tax_bit})",
            category="government",
        )
    if paid:
        await db.flush()
    return paid
