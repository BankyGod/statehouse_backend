"""Thin state-owned enterprises — seed + read API."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import (
    EnterpriseKind,
    EnterprisePortfolio,
    StateEnterprise,
)
from app.models.state import State
from app.models.stock import StockIssuerType, StockListing

# slug, name, kind, portfolio, home_state_slug|None, stock_symbol|None, description
ENTERPRISE_SEED: list[tuple] = [
    # Passenger transport SOEs (2 air + 2 rail + 2 coach) — fares credit these ledgers
    (
        "uaair",
        "AmirAir",
        EnterpriseKind.AIR,
        EnterprisePortfolio.TRANSPORT,
        "amira-central",
        "UAAIR",
        "National flag airline — inter-capital air service.",
    ),
    (
        "uasky",
        "SkyLink National",
        EnterpriseKind.AIR,
        EnterprisePortfolio.TRANSPORT,
        "port-meridian",
        "UASKY",
        "Second state airline — denser domestic routes.",
    ),
    (
        "uanrl",
        "United Amir National Rail",
        EnterpriseKind.RAIL,
        EnterprisePortfolio.TRANSPORT,
        "railford",
        "UANRL",
        "National passenger and freight rail backbone.",
    ),
    (
        "uaexp",
        "Amir Express Rail",
        EnterpriseKind.RAIL,
        EnterprisePortfolio.TRANSPORT,
        "amira-central",
        "UAEXP",
        "State high-speed passenger rail corridors.",
    ),
    (
        "uacch",
        "State Coach",
        EnterpriseKind.BUS,
        EnterprisePortfolio.TRANSPORT,
        "railford",
        "UACCH",
        "National public coach network — town-to-town.",
    ),
    (
        "uabus",
        "National Highway Coaches",
        EnterpriseKind.BUS,
        EnterprisePortfolio.TRANSPORT,
        "port-meridian",
        "UABUS",
        "State highway coach line — reserved long-haul seats.",
    ),
    (
        "uaegy",
        "Amir Energy Board",
        EnterpriseKind.POWER,
        EnterprisePortfolio.ENERGY,
        "blackreef",
        "UAEGY",
        "National generation and transmission grid.",
    ),
    (
        "uaprt",
        "United Amir Port Authority",
        EnterpriseKind.PORT,
        EnterprisePortfolio.TRANSPORT,
        "port-meridian",
        "UAPRT",
        "Main deep-water ports and customs terminals.",
    ),
    (
        "uanus",
        "United Amir National University System",
        EnterpriseKind.UNIVERSITY_SYSTEM,
        EnterprisePortfolio.EDUCATION,
        "amira-central",
        "UANUS",
        "Public universities and polytechnics under the Education ministry.",
    ),
]

# Launch prices for a young exchange (hard-reprice target)
GOV_LAUNCH_PRICES: dict[str, tuple[float, int]] = {
    "UAAIR": (4.5, 28_000),
    "UASKY": (3.8, 22_000),
    "UANRL": (4.0, 30_000),
    "UAEXP": (4.2, 24_000),
    "UACCH": (2.8, 18_000),
    "UABUS": (3.0, 18_000),
    "UAEGY": (5.0, 40_000),
    "UAPRT": (3.5, 20_000),
    "UANUS": (2.5, 25_000),
}


async def ensure_enterprises_seeded(db: AsyncSession) -> int:
    """Upsert every seed SOE by slug (adds new transport operators on existing DBs)."""
    states = {
        s.slug: s for s in (await db.execute(select(State))).scalars().all()
    }
    listings = {
        L.symbol: L
        for L in (
            await db.execute(
                select(StockListing).where(
                    StockListing.issuer_type == StockIssuerType.GOVERNMENT
                )
            )
        )
        .scalars()
        .all()
    }

    created = 0
    for slug, name, kind, portfolio, state_slug, symbol, desc in ENTERPRISE_SEED:
        home = states.get(state_slug) if state_slug else None
        listing = listings.get(symbol) if symbol else None
        ent = (
            await db.execute(select(StateEnterprise).where(StateEnterprise.slug == slug))
        ).scalar_one_or_none()
        if ent is None:
            ent = StateEnterprise(
                slug=slug,
                name=name,
                kind=kind,
                portfolio=portfolio,
                description=desc,
                home_state_id=home.id if home else None,
                stock_listing_id=listing.id if listing else None,
                is_active=True,
            )
            db.add(ent)
            await db.flush()
            created += 1
        else:
            ent.name = name
            ent.kind = kind
            ent.portfolio = portfolio
            ent.description = desc
            ent.is_active = True
            if home and ent.home_state_id is None:
                ent.home_state_id = home.id
            if listing and ent.stock_listing_id is None:
                ent.stock_listing_id = listing.id
    await db.flush()
    await _link_stock_listings(db)
    return created


async def _link_stock_listings(db: AsyncSession) -> None:
    listings = {
        L.symbol: L
        for L in (
            await db.execute(
                select(StockListing).where(
                    StockListing.issuer_type == StockIssuerType.GOVERNMENT
                )
            )
        )
        .scalars()
        .all()
    }
    for slug, _n, _k, _p, _s, symbol, _d in ENTERPRISE_SEED:
        if not symbol:
            continue
        listing = listings.get(symbol)
        if not listing:
            continue
        ent = (
            await db.execute(select(StateEnterprise).where(StateEnterprise.slug == slug))
        ).scalar_one_or_none()
        if ent:
            if ent.stock_listing_id is None:
                ent.stock_listing_id = listing.id
            if getattr(listing, "enterprise_id", None) is None:
                listing.enterprise_id = ent.id
    await db.flush()


async def list_enterprises(db: AsyncSession) -> list[dict]:
    await ensure_enterprises_seeded(db)
    result = await db.execute(
        select(StateEnterprise).where(StateEnterprise.is_active.is_(True)).order_by(
            StateEnterprise.id
        )
    )
    out = []
    for e in result.scalars().all():
        symbol = None
        if e.stock_listing_id:
            listing = await db.get(StockListing, e.stock_listing_id)
            symbol = listing.symbol if listing else None
        out.append(
            {
                "id": e.id,
                "slug": e.slug,
                "name": e.name,
                "kind": e.kind.value,
                "portfolio": e.portfolio.value,
                "description": e.description,
                "home_state_id": e.home_state_id,
                "stock_symbol": symbol,
                "cash_balance": float(e.cash_balance or 0),
                "lifetime_revenue": float(e.lifetime_revenue or 0),
                "lifetime_costs": float(e.lifetime_costs or 0),
                "ownership": "government",
                "is_active": e.is_active,
            }
        )
    return out


async def tick_enterprise_operations(db: AsyncSession) -> dict:
    """
    Light SOE operating costs/revenue from the living world.
    Travel/tuition already credit ledgers; this adds grid demand + opex.
    """
    from sqlalchemy import func

    from app.core.game_time import utcnow
    from app.models.state import State

    now = utcnow()
    result = await db.execute(
        select(StateEnterprise).where(StateEnterprise.is_active.is_(True))
    )
    touched = 0
    for ent in result.scalars().all():
        last = ent.last_ops_at
        if last is not None:
            if getattr(last, "tzinfo", None) is None:
                from datetime import timezone

                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < 3600:
                continue

        opex = 25.0
        revenue = 0.0
        if ent.kind == EnterpriseKind.POWER:
            pop = float(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(State.population_count), 0))
                    )
                ).scalar_one()
                or 0
            )
            # Grid fee from population demand
            revenue = round(max(10.0, pop * 0.002), 2)
            opex = round(max(15.0, pop * 0.0012), 2)
        elif ent.kind == EnterpriseKind.RAIL:
            opex = 40.0
        elif ent.kind == EnterpriseKind.AIR:
            opex = 55.0
        elif ent.kind == EnterpriseKind.BUS:
            opex = 28.0
        elif ent.kind == EnterpriseKind.PORT:
            opex = 35.0
        elif ent.kind == EnterpriseKind.UNIVERSITY_SYSTEM:
            opex = 30.0

        cash = float(ent.cash_balance or 0)
        if revenue > 0:
            cash += revenue
            ent.lifetime_revenue = round(float(ent.lifetime_revenue or 0) + revenue, 2)
        paid_opex = min(opex, cash)
        cash = round(cash - paid_opex, 2)
        ent.lifetime_costs = round(float(ent.lifetime_costs or 0) + paid_opex, 2)
        ent.cash_balance = cash
        ent.last_ops_at = now
        touched += 1

        # Feed stock fundamentals with real ledger profit
        if ent.stock_listing_id and (revenue > 0 or paid_opex > 0):
            from app.models.stock import StockListing, StockListingStatus
            from app.services import performance_service, stock_service

            listing = await db.get(StockListing, ent.stock_listing_id)
            if listing and listing.status == StockListingStatus.ACTIVE:
                profit = revenue - paid_opex
                base = max(cash, listing.share_price * 20, 100.0)
                pct = max(-0.03, min(0.03, (profit / base) * 0.08))
                reason = stock_service._apply_pct_move(listing, pct)
                await performance_service.record_price_point(
                    db, listing, reason=f"soe_{reason}"
                )

    if touched:
        await db.flush()
    return {"enterprises": touched}


async def get_by_slug(db: AsyncSession, slug: str) -> StateEnterprise | None:
    result = await db.execute(
        select(StateEnterprise).where(StateEnterprise.slug == slug)
    )
    return result.scalar_one_or_none()
