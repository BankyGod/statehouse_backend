from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.cabinet import PORTFOLIO_LABELS, CabinetSeat, Portfolio
from app.models.character import Character
from app.models.state import State
from app.services import news_service, politics_service
from app.services.character_service import ensure_can_act

NPC_MINISTERS = {
    Portfolio.FINANCE: "Hon. Efua Mensah (NPC)",
    Portfolio.DEFENCE: "Hon. Kwame Boateng (NPC)",
    Portfolio.HEALTH: "Hon. Dr. Akosua Darko (NPC)",
    Portfolio.EDUCATION: "Hon. Yaa Asantewa (NPC)",
    Portfolio.INTERIOR: "Hon. Ibrahim Yusuf (NPC)",
    Portfolio.TRADE: "Hon. Nadia Owusu (NPC)",
    Portfolio.JUSTICE: "Hon. Justice Kofi Adjei (NPC)",
    Portfolio.AGRICULTURE: "Hon. Ama Serwaa-Bediako (NPC)",
    Portfolio.ENERGY: "Hon. Daniel Okoro (NPC)",
    Portfolio.TRANSPORT: "Hon. Grace Addo (NPC)",
}


async def ensure_cabinet_seeded(db: AsyncSession) -> int:
    result = await db.execute(select(CabinetSeat.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0
    now = utcnow()
    for portfolio, npc in NPC_MINISTERS.items():
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
    await db.flush()
    return len(NPC_MINISTERS)


async def list_cabinet(db: AsyncSession) -> list[dict]:
    await ensure_cabinet_seeded(db)
    result = await db.execute(select(CabinetSeat).order_by(CabinetSeat.id))
    seats = []
    for seat in result.scalars().all():
        name = seat.npc_name
        if seat.character_id:
            ch = await db.get(Character, seat.character_id)
            name = ch.display_name if ch else name
        seats.append(
            {
                "id": seat.id,
                "portfolio": seat.portfolio.value,
                "title": seat.title,
                "character_id": seat.character_id,
                "name": name,
                "is_npc": seat.is_npc,
                "appointed_at": seat.appointed_at,
            }
        )
    return seats


async def _require_president(db: AsyncSession, character: Character) -> None:
    nation = await politics_service.get_or_create_nation(db)
    if nation.president_character_id != character.id:
        raise HTTPException(
            status_code=403, detail="Only the sitting President can manage the cabinet"
        )


async def _is_mp(db: AsyncSession, character_id: int) -> bool:
    result = await db.execute(
        select(State.id).where(State.mp_character_id == character_id)
    )
    return result.scalar_one_or_none() is not None


async def appoint(
    db: AsyncSession,
    president: Character,
    portfolio: Portfolio,
    appointee_id: int,
) -> dict:
    ensure_can_act(president)
    await _require_president(db, president)
    settings = get_settings()

    if appointee_id == president.id:
        raise HTTPException(status_code=400, detail="President cannot hold a ministry")

    appointee = await db.get(Character, appointee_id)
    if appointee is None:
        raise HTTPException(status_code=404, detail="Character not found")
    if appointee.heat >= settings.max_heat_to_run:
        raise HTTPException(status_code=400, detail="Appointee heat too high")
    if settings.cabinet_require_mp and not await _is_mp(db, appointee_id):
        raise HTTPException(
            status_code=400, detail="Ministers must be sitting MPs"
        )

    # One ministry per person
    held = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.character_id == appointee_id,
            CabinetSeat.is_npc.is_(False),
        )
    )
    if held.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already holds a cabinet post")

    result = await db.execute(
        select(CabinetSeat).where(CabinetSeat.portfolio == portfolio)
    )
    seat = result.scalar_one_or_none()
    if seat is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Restore previous player minister reputation note only
    now = utcnow()
    seat.character_id = appointee_id
    seat.is_npc = False
    seat.npc_name = None
    seat.appointed_at = now
    seat.last_salary_at = now
    appointee.reputation += 15

    await news_service.publish(
        db,
        f"Cabinet: {PORTFOLIO_LABELS[portfolio]}",
        f"{appointee.display_name} appointed by President {president.display_name}.",
        category="politics",
    )
    await db.flush()
    return {
        "portfolio": portfolio.value,
        "title": seat.title,
        "character_id": appointee_id,
        "name": appointee.display_name,
        "is_npc": False,
    }


async def dismiss(
    db: AsyncSession, president: Character, portfolio: Portfolio
) -> dict:
    ensure_can_act(president)
    await _require_president(db, president)

    result = await db.execute(
        select(CabinetSeat).where(CabinetSeat.portfolio == portfolio)
    )
    seat = result.scalar_one_or_none()
    if seat is None or seat.is_npc:
        raise HTTPException(status_code=400, detail="No player minister to dismiss")

    old_id = seat.character_id
    old = await db.get(Character, old_id) if old_id else None
    npc = NPC_MINISTERS[portfolio]
    seat.character_id = None
    seat.is_npc = True
    seat.npc_name = npc
    seat.appointed_at = utcnow()
    if old:
        old.reputation = max(-100, old.reputation - 10)

    await news_service.publish(
        db,
        f"Cabinet shuffle: {seat.title}",
        f"{old.display_name if old else 'A minister'} was dismissed. {npc} returns as caretaker.",
        category="politics",
    )
    await db.flush()
    return {"portfolio": portfolio.value, "name": npc, "is_npc": True}


async def resign(db: AsyncSession, character: Character) -> dict:
    ensure_can_act(character)
    result = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.character_id == character.id,
            CabinetSeat.is_npc.is_(False),
        )
    )
    seat = result.scalar_one_or_none()
    if seat is None:
        raise HTTPException(status_code=400, detail="You do not hold a ministry")

    portfolio = seat.portfolio
    npc = NPC_MINISTERS[portfolio]
    seat.character_id = None
    seat.is_npc = True
    seat.npc_name = npc
    seat.appointed_at = utcnow()
    character.reputation = max(-100, character.reputation - 5)

    await news_service.publish(
        db,
        f"Resignation: {seat.title}",
        f"{character.display_name} resigned from cabinet.",
        category="politics",
    )
    await db.flush()
    return {"portfolio": portfolio.value, "message": "Resigned", "npc_caretaker": npc}


async def my_portfolio(db: AsyncSession, character: Character) -> dict | None:
    result = await db.execute(
        select(CabinetSeat).where(CabinetSeat.character_id == character.id)
    )
    seat = result.scalar_one_or_none()
    if seat is None:
        return None
    return {
        "portfolio": seat.portfolio.value,
        "title": seat.title,
        "appointed_at": seat.appointed_at,
        "weekly_salary": get_settings().minister_weekly_salary,
    }


async def pay_minister_salaries(db: AsyncSession) -> int:
    """Weekly cabinet pay for player ministers."""
    settings = get_settings()
    now = utcnow()
    result = await db.execute(
        select(CabinetSeat).where(
            CabinetSeat.is_npc.is_(False),
            CabinetSeat.character_id.is_not(None),
        )
    )
    paid = 0
    for seat in result.scalars().all():
        last = seat.last_salary_at or seat.appointed_at or now
        if last.tzinfo is None:
            from datetime import timezone

            last = last.replace(tzinfo=timezone.utc)
        if now < last + timedelta(days=7):
            continue
        ch = await db.get(Character, seat.character_id)
        if ch is None:
            continue
        ch.cash += settings.minister_weekly_salary
        seat.last_salary_at = now
        paid += 1
    if paid:
        await db.flush()
    return paid
