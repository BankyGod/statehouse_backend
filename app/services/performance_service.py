"""Company performance scoring, IPO readiness, and ops-driven stock prices."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.business import Business, BusinessStatus
from app.models.character import Character
from app.models.employee import BusinessEmployee
from app.models.performance import BusinessPerformanceSnapshot, StockPricePoint
from app.models.stock import StockListing, StockListingStatus


def compute_performance_score(
    *,
    age_days: float,
    cash: float,
    lifetime_revenue: float,
    lifetime_wages: float,
    employee_count: int,
) -> float:
    net = lifetime_revenue - lifetime_wages
    score = 0.0
    score += min(25.0, max(0.0, age_days) * 3.0)
    score += min(25.0, max(0.0, cash) / 200.0)
    score += min(25.0, max(0.0, lifetime_revenue) / 200.0)
    score += min(15.0, max(0.0, net) / 100.0)
    score += min(10.0, max(0, employee_count) * 2.0)
    return round(min(100.0, score), 1)


async def employee_count(db: AsyncSession, business_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(BusinessEmployee)
        .where(
            BusinessEmployee.business_id == business_id,
            BusinessEmployee.is_active.is_(True),
        )
    )
    return int(result.scalar_one() or 0)


def business_age_days(business: Business) -> float:
    if not business.registered_at:
        return 0.0
    reg = business.registered_at
    if reg.tzinfo is None:
        from datetime import timezone

        reg = reg.replace(tzinfo=timezone.utc)
    return max(0.0, (utcnow() - reg).total_seconds() / 86400.0)


async def score_business(db: AsyncSession, business: Business) -> dict:
    staff = await employee_count(db, business.id)
    age = business_age_days(business)
    rev = float(business.lifetime_revenue or 0)
    wages = float(business.lifetime_wages or 0)
    cash = float(business.cash_balance or 0)
    net = round(rev - wages, 2)
    score = compute_performance_score(
        age_days=age,
        cash=cash,
        lifetime_revenue=rev,
        lifetime_wages=wages,
        employee_count=staff,
    )
    return {
        "age_days": round(age, 2),
        "cash_balance": cash,
        "lifetime_revenue": rev,
        "lifetime_wages": wages,
        "net_profit": net,
        "employee_count": staff,
        "performance_score": score,
    }


async def ipo_checklist(db: AsyncSession, character: Character, business: Business) -> dict:
    settings = get_settings()
    m = await score_business(db, business)
    checks = [
        {
            "key": "active",
            "label": "Company is active",
            "ok": business.status == BusinessStatus.ACTIVE,
            "detail": business.status.value if hasattr(business.status, "value") else str(business.status),
        },
        {
            "key": "not_public",
            "label": "Not already listed",
            "ok": not business.is_public,
            "detail": "Already public" if business.is_public else "Private",
        },
        {
            "key": "age",
            "label": f"Age ≥ {settings.stock_ipo_min_business_age_days:.0f} days",
            "ok": m["age_days"] >= settings.stock_ipo_min_business_age_days,
            "detail": f"{m['age_days']:.1f} days",
        },
        {
            "key": "cash",
            "label": f"Treasury ≥ ${settings.stock_ipo_min_business_cash:.0f}",
            "ok": m["cash_balance"] >= settings.stock_ipo_min_business_cash,
            "detail": f"${m['cash_balance']:.2f}",
        },
        {
            "key": "revenue",
            "label": f"Lifetime revenue ≥ ${settings.stock_ipo_min_lifetime_revenue:.0f}",
            "ok": m["lifetime_revenue"] >= settings.stock_ipo_min_lifetime_revenue,
            "detail": f"${m['lifetime_revenue']:.2f}",
        },
        {
            "key": "profit",
            "label": f"Net (rev − wages) ≥ ${settings.stock_ipo_min_net_profit:.0f}",
            "ok": m["net_profit"] >= settings.stock_ipo_min_net_profit,
            "detail": f"${m['net_profit']:.2f}",
        },
        {
            "key": "staff",
            "label": f"Active staff ≥ {settings.stock_ipo_min_employees}",
            "ok": m["employee_count"] >= settings.stock_ipo_min_employees,
            "detail": str(m["employee_count"]),
        },
        {
            "key": "score",
            "label": f"Performance score ≥ {settings.stock_ipo_min_performance_score:.0f}",
            "ok": m["performance_score"] >= settings.stock_ipo_min_performance_score,
            "detail": f"{m['performance_score']:.1f}/100",
        },
        {
            "key": "reputation",
            "label": f"Owner reputation ≥ {settings.stock_ipo_min_owner_reputation}",
            "ok": character.reputation >= settings.stock_ipo_min_owner_reputation,
            "detail": str(character.reputation),
        },
        {
            "key": "heat",
            "label": "Owner heat < 30",
            "ok": character.heat < 30,
            "detail": f"{character.heat:.0f}",
        },
        {
            "key": "clean",
            "label": "No criminal record",
            "ok": not bool(character.criminal_record_summary),
            "detail": "Clean" if not character.criminal_record_summary else "Record on file",
        },
    ]
    eligible = all(c["ok"] for c in checks)
    return {"eligible": eligible, "checks": checks, "metrics": m}


async def record_snapshot(
    db: AsyncSession,
    business: Business,
    *,
    interval_revenue: float = 0.0,
    interval_wages: float = 0.0,
) -> BusinessPerformanceSnapshot:
    m = await score_business(db, business)
    snap = BusinessPerformanceSnapshot(
        business_id=business.id,
        cash_balance=m["cash_balance"],
        lifetime_revenue=m["lifetime_revenue"],
        lifetime_wages=m["lifetime_wages"],
        employee_count=m["employee_count"],
        interval_revenue=round(float(interval_revenue), 2),
        interval_wages=round(float(interval_wages), 2),
        performance_score=m["performance_score"],
        posted_at=utcnow(),
    )
    db.add(snap)
    await db.flush()
    return snap


async def record_price_point(
    db: AsyncSession,
    listing: StockListing,
    *,
    reason: str,
) -> StockPricePoint:
    point = StockPricePoint(
        listing_id=listing.id,
        price=round(float(listing.share_price), 4),
        reason=reason,
        posted_at=utcnow(),
    )
    db.add(point)
    await db.flush()
    return point


async def apply_ops_to_stock_price(
    db: AsyncSession,
    business: Business,
    *,
    interval_revenue: float,
    interval_wages: float,
) -> float | None:
    """Move public share price from real ops profit/loss. Returns new price or None."""
    if not business.is_public or not business.stock_listing_id:
        return None
    listing = await db.get(StockListing, business.stock_listing_id)
    if listing is None or listing.status != StockListingStatus.ACTIVE:
        return None

    settings = get_settings()
    profit = float(interval_revenue) - float(interval_wages)
    base = max(float(business.cash_balance), float(listing.share_price) * 10, 100.0)
    raw = profit / base
    sens = settings.stock_ops_price_sensitivity
    pct = max(-sens, min(sens, raw * sens * 8))
    if abs(pct) < 0.0005:
        # Still record a flat tick so charts advance with company activity
        await record_price_point(db, listing, reason="ops_flat")
        return listing.share_price

    old = listing.share_price
    floor = float(settings.stock_price_floor)
    listing.share_price = round(max(floor, old * (1.0 + pct)), 4)
    listing.is_booming = profit > 0 and listing.share_price >= old
    reason = "ops_up" if listing.share_price >= old else "ops_down"
    await record_price_point(db, listing, reason=reason)
    return listing.share_price


async def performance_dashboard(
    db: AsyncSession, character: Character, business_id: int
) -> dict:
    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")

    checklist = await ipo_checklist(db, character, business)
    snaps = await db.execute(
        select(BusinessPerformanceSnapshot)
        .where(BusinessPerformanceSnapshot.business_id == business_id)
        .order_by(BusinessPerformanceSnapshot.id.desc())
        .limit(48)
    )
    history = list(reversed(list(snaps.scalars().all())))

    stock = None
    price_history: list[dict] = []
    if business.stock_listing_id:
        listing = await db.get(StockListing, business.stock_listing_id)
        if listing:
            stock = {
                "listing_id": listing.id,
                "symbol": listing.symbol,
                "share_price": listing.share_price,
                "float_shares": listing.float_shares,
                "founder_shares": listing.founder_shares,
                "ipo_raised": listing.ipo_raised,
                "is_booming": listing.is_booming,
                "listed_at": listing.listed_at,
            }
            pts = await db.execute(
                select(StockPricePoint)
                .where(StockPricePoint.listing_id == listing.id)
                .order_by(StockPricePoint.id.desc())
                .limit(120)
            )
            price_history = [
                {
                    "t": int(p.posted_at.timestamp() * 1000),
                    "price": p.price,
                    "reason": p.reason,
                }
                for p in reversed(list(pts.scalars().all()))
            ]

    return {
        "business_id": business.id,
        "name": business.name,
        "sector": business.sector,
        "status": business.status.value if hasattr(business.status, "value") else str(business.status),
        "is_public": business.is_public,
        "metrics": checklist["metrics"],
        "ipo": {
            "eligible": checklist["eligible"],
            "checks": checklist["checks"],
            "listing_fee": get_settings().stock_ipo_listing_fee,
        },
        "performance_history": [
            {
                "t": int(s.posted_at.timestamp() * 1000),
                "cash_balance": s.cash_balance,
                "lifetime_revenue": s.lifetime_revenue,
                "lifetime_wages": s.lifetime_wages,
                "interval_revenue": s.interval_revenue,
                "interval_wages": s.interval_wages,
                "employee_count": s.employee_count,
                "performance_score": s.performance_score,
            }
            for s in history
        ],
        "stock": stock,
        "price_history": price_history,
    }


async def listing_price_history(
    db: AsyncSession, listing_id: int, *, limit: int = 120
) -> list[dict]:
    pts = await db.execute(
        select(StockPricePoint)
        .where(StockPricePoint.listing_id == listing_id)
        .order_by(StockPricePoint.id.desc())
        .limit(limit)
    )
    rows = list(reversed(list(pts.scalars().all())))
    if not rows:
        listing = await db.get(StockListing, listing_id)
        if listing is None:
            return []
        # Bootstrap one tick so charts aren't empty for pre-history listings
        point = await record_price_point(db, listing, reason="bootstrap")
        return [
            {
                "t": int(point.posted_at.timestamp() * 1000),
                "price": point.price,
                "reason": point.reason,
            }
        ]
    return [
        {
            "t": int(p.posted_at.timestamp() * 1000),
            "price": p.price,
            "reason": p.reason,
        }
        for p in rows
    ]
