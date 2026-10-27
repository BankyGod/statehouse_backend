from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.housing import HousingListing
from app.models.job import JobListing
from app.models.legislation import NewsItem
from app.models.politics import Election
from app.models.state import State
from app.seed.housing_data import HOUSING_TEMPLATES
from app.seed.jobs_data import JOB_TEMPLATES
from app.seed.states_data import STATES
from app.services import (
    cabinet_service,
    legislation_service,
    living_world_service,
    news_service,
    politics_service,
    stock_service,
)


async def seed_states(db: AsyncSession) -> int:
    result = await db.execute(select(State.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0

    for data in STATES:
        db.add(State(**data, population_count=0, is_open=True))
    await db.flush()
    return len(STATES)


async def seed_jobs(db: AsyncSession) -> int:
    result = await db.execute(select(JobListing.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0

    states_result = await db.execute(select(State))
    states = {s.slug: s for s in states_result.scalars().all()}
    created = 0

    for template in JOB_TEMPLATES:
        target_slugs = template["states"]
        if target_slugs is None:
            target_states = list(states.values())
        else:
            target_states = [states[s] for s in target_slugs if s in states]

        for state in target_states:
            db.add(
                JobListing(
                    state_id=state.id,
                    title=template["title"],
                    sector=template["sector"],
                    description=template["description"],
                    wage_per_shift=template["wage_per_shift"],
                    energy_cost=template["energy_cost"],
                    shift_minutes=template["shift_minutes"],
                    min_education_level=template["min_education_level"],
                    requires_clean_record=template["requires_clean_record"],
                    is_active=True,
                )
            )
            created += 1

    await db.flush()
    return created


async def seed_housing(db: AsyncSession) -> int:
    result = await db.execute(select(HousingListing.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0

    states_result = await db.execute(select(State))
    states = list(states_result.scalars().all())
    created = 0

    for state in states:
        income = max(state.average_income, 800.0)
        for template in HOUSING_TEMPLATES:
            weekly = round(income * template["rent_factor"], 2)
            buy_price = None
            if template.get("buy_price_factor"):
                buy_price = round(income * template["buy_price_factor"], 2)
            from app.models.housing import HousingOwnership

            db.add(
                HousingListing(
                    state_id=state.id,
                    title=template["title"],
                    kind=template["kind"],
                    description=template["description"],
                    weekly_rent=weekly,
                    buy_price=buy_price,
                    energy_bonus=template["energy_bonus"],
                    home_state_only=template["home_state_only"],
                    is_available=True,
                    ownership=HousingOwnership.GOVERNMENT.value,
                    owner_business_id=None,
                )
            )
            created += 1

    await db.flush()
    return created


async def seed_politics(db: AsyncSession) -> int:
    result = await db.execute(select(Election.id).limit(1))
    if result.scalar_one_or_none() is not None:
        await politics_service.get_or_create_nation(db)
        return 0
    # Open voting immediately so FE can test without waiting 21 days
    await politics_service.create_election_cycle(db, force_voting=True)
    return 1


async def seed_news_and_budget(db: AsyncSession) -> dict[str, int]:
    news_count = 0
    result = await db.execute(select(NewsItem.id).limit(1))
    if result.scalar_one_or_none() is None:
        await news_service.publish(
            db,
            "United Amir opens its doors",
            "Twenty states welcome new citizens. Choose a home, find work, build a life.",
            category="general",
        )
        await news_service.publish(
            db,
            "Parliament sits with NPC caretakers",
            "Until players win seats, NPC MPs hold the 20 constituencies. Majority is 11.",
            category="politics",
        )
        await news_service.publish(
            db,
            "Five parties open membership rolls",
            "UPA, NPP, APU, GHM, and CCP welcome citizens. Civil service posts remain NPC-staffed until players apply.",
            category="politics",
        )
        news_count = 3

    budget = await legislation_service.get_current_budget(db)
    budget_count = 1 if budget else 0
    return {"news": news_count, "budget": budget_count}


async def seed_cabinet(db: AsyncSession) -> int:
    return await cabinet_service.ensure_cabinet_seeded(db)


async def seed_living_world(db: AsyncSession) -> dict:
    """NPC president/VP/speaker, parties, civil service, fill gaps."""
    return await living_world_service.ensure_living_government(db)


async def seed_npc_citizens(db: AsyncSession) -> dict:
    """Automated citizens that populate states and act like players."""
    from app.services import npc_sim_service

    return await npc_sim_service.ensure_npc_citizens(db)


async def seed_stocks(db: AsyncSession) -> int:
    return await stock_service.seed_government_listings(db)


async def seed_enterprises(db: AsyncSession) -> int:
    from app.services import enterprise_service

    return await enterprise_service.ensure_enterprises_seeded(db)


async def seed_education(db: AsyncSession) -> int:
    from app.services import education_service

    return await education_service.ensure_education_seeded(db)


async def seed_carriers(db: AsyncSession) -> int:
    from app.services import travel_service

    return await travel_service.ensure_carriers_seeded(db)


async def seed_mogul(db: AsyncSession) -> dict:
    from app.seed.demo_mogul import seed_demo_mogul

    return await seed_demo_mogul(db)


async def seed_events(db: AsyncSession) -> int:
    from app.services import social_service

    return await social_service.seed_world_events(db)


async def run_seed(db: AsyncSession) -> dict:
    states = await seed_states(db)
    jobs = await seed_jobs(db)
    housing = await seed_housing(db)
    politics = await seed_politics(db)
    cabinet = await seed_cabinet(db)
    living = await seed_living_world(db)
    npc_citizens = await seed_npc_citizens(db)
    enterprises = await seed_enterprises(db)
    stocks = await seed_stocks(db)
    education = await seed_education(db)
    carriers = await seed_carriers(db)
    extra = await seed_news_and_budget(db)
    events = await seed_events(db)
    mogul = await seed_mogul(db)
    return {
        "states": states,
        "jobs": jobs,
        "housing": housing,
        "politics": politics,
        "cabinet": cabinet,
        "living_world": living,
        "npc_citizens": npc_citizens,
        "stocks": stocks,
        "enterprises": enterprises,
        "education_programs": education,
        "carriers": carriers,
        "events": events,
        "mogul": mogul,
        **extra,
    }
