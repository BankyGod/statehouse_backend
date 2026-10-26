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
        None,
        "Public universities and polytechnics under the Education ministry.",
    ),
]


async def ensure_enterprises_seeded(db: AsyncSession) -> int:
    result = await db.execute(select(StateEnterprise.id).limit(1))
    if result.scalar_one_or_none() is not None:
        # Still try to link any missing stock listings
        await _link_stock_listings(db)
        return 0

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
        db.add(
            StateEnterprise(
                slug=slug,
                name=name,
                kind=kind,
                portfolio=portfolio,
                description=desc,
                home_state_id=home.id if home else None,
                stock_listing_id=listing.id if listing else None,
                is_active=True,
            )
        )
        created += 1
    await db.flush()
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
        if ent and ent.stock_listing_id is None:
            ent.stock_listing_id = listing.id
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
                "ownership": "government",
                "is_active": e.is_active,
            }
        )
    return out


async def get_by_slug(db: AsyncSession, slug: str) -> StateEnterprise | None:
    result = await db.execute(
        select(StateEnterprise).where(StateEnterprise.slug == slug)
    )
    return result.scalar_one_or_none()
