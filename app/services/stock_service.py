"""Stock exchange — separate from banking.

Rules:
- Business IPO: must meet cash/age/reputation requirements; pays listing fee.
- Primary sales: buyer pays → business (or gov treasury) receives IPO capital once.
- Secondary sales: shareholder sells to another player; business does NOT touch that money.
- Owner cannot seize or "withdraw" investor share value — exit is only sell shares.
"""

from datetime import timedelta
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.business import Business, BusinessStatus
from app.models.character import Character
from app.models.stock import (
    ShareHolding,
    StockIssuerType,
    StockListing,
    StockListingStatus,
    StockTrade,
)
from app.services.character_service import ensure_can_act
from app.services import news_service, politics_service

_SYMBOL_RE = re.compile(r"^[A-Z]{2,8}$")


async def _get_holding(
    db: AsyncSession, character_id: int, listing_id: int
) -> ShareHolding | None:
    result = await db.execute(
        select(ShareHolding).where(
            ShareHolding.character_id == character_id,
            ShareHolding.listing_id == listing_id,
        )
    )
    return result.scalar_one_or_none()


async def _ensure_holding(
    db: AsyncSession, character_id: int, listing_id: int
) -> ShareHolding:
    holding = await _get_holding(db, character_id, listing_id)
    if holding:
        return holding
    holding = ShareHolding(
        character_id=character_id, listing_id=listing_id, shares=0, avg_cost=0.0
    )
    db.add(holding)
    await db.flush()
    return holding


def _add_shares(holding: ShareHolding, qty: int, price: float) -> None:
    if qty <= 0:
        return
    total_cost = holding.avg_cost * holding.shares + price * qty
    holding.shares += qty
    holding.avg_cost = round(total_cost / holding.shares, 4) if holding.shares else 0.0


def _remove_shares(holding: ShareHolding, qty: int) -> None:
    if qty > holding.shares:
        raise HTTPException(status_code=400, detail="Not enough shares")
    holding.shares -= qty
    if holding.shares == 0:
        holding.avg_cost = 0.0


def _bump_price(listing: StockListing, shares: int, *, buying: bool) -> None:
    settings = get_settings()
    impact = listing.share_price * settings.stock_price_impact * shares
    if listing.is_booming:
        impact *= 1.5
    if buying:
        listing.share_price = round(listing.share_price + impact, 4)
    else:
        listing.share_price = round(max(0.5, listing.share_price - impact), 4)


async def list_market(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(StockListing)
        .where(StockListing.status == StockListingStatus.ACTIVE)
        .order_by(StockListing.symbol)
    )
    out = []
    for L in result.scalars().all():
        out.append(
            {
                "id": L.id,
                "symbol": L.symbol,
                "name": L.name,
                "issuer_type": L.issuer_type.value,
                "business_id": L.business_id,
                "description": L.description,
                "share_price": L.share_price,
                "total_shares": L.total_shares,
                "float_shares": L.float_shares,
                "founder_shares": L.founder_shares,
                "ipo_raised": L.ipo_raised,
                "is_booming": L.is_booming,
                "listed_at": L.listed_at,
            }
        )
    return out


async def my_portfolio(db: AsyncSession, character: Character) -> list[dict]:
    result = await db.execute(
        select(ShareHolding).where(
            ShareHolding.character_id == character.id,
            ShareHolding.shares > 0,
        )
    )
    out = []
    for h in result.scalars().all():
        listing = await db.get(StockListing, h.listing_id)
        if listing is None:
            continue
        market_value = round(h.shares * listing.share_price, 2)
        cost_basis = round(h.shares * h.avg_cost, 2)
        out.append(
            {
                "listing_id": listing.id,
                "symbol": listing.symbol,
                "name": listing.name,
                "shares": h.shares,
                "avg_cost": h.avg_cost,
                "share_price": listing.share_price,
                "market_value": market_value,
                "unrealized_pnl": round(market_value - cost_basis, 2),
            }
        )
    return out


async def ipo_business(
    db: AsyncSession,
    character: Character,
    business_id: int,
    *,
    symbol: str,
    total_shares: int,
    ipo_price: float,
    founder_keep_pct: float = 0.4,
) -> StockListing:
    """List a booming/eligible business. Capital raised stays in business cash — not owner pocket as 'shares'."""
    ensure_can_act(character)
    settings = get_settings()

    business = await db.get(Business, business_id)
    if business is None or business.owner_id != character.id:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.status != BusinessStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Business must be active")
    if business.is_public:
        raise HTTPException(status_code=400, detail="Already publicly listed")

    if business.cash_balance < settings.stock_ipo_min_business_cash:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least ${settings.stock_ipo_min_business_cash:.0f} business cash to IPO",
        )
    if not business.registered_at:
        raise HTTPException(status_code=400, detail="Business not fully registered")

    reg = business.registered_at
    if reg.tzinfo is None:
        from datetime import timezone

        reg = reg.replace(tzinfo=timezone.utc)
    age_days = (utcnow() - reg).total_seconds() / 86400.0
    if age_days < settings.stock_ipo_min_business_age_days:
        raise HTTPException(
            status_code=400,
            detail=f"Business must be at least {settings.stock_ipo_min_business_age_days} days old",
        )

    if character.reputation < settings.stock_ipo_min_owner_reputation:
        raise HTTPException(
            status_code=400,
            detail=f"Owner reputation must be ≥ {settings.stock_ipo_min_owner_reputation}",
        )
    if character.heat >= 30:
        raise HTTPException(status_code=403, detail="Heat too high for IPO")
    if character.criminal_record_summary:
        raise HTTPException(status_code=403, detail="Criminal record blocks IPO")

    sym = symbol.strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=400, detail="Symbol must be 2–8 letters A–Z")
    if (
        total_shares < settings.stock_ipo_min_shares
        or total_shares > settings.stock_ipo_max_shares
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Shares must be between {settings.stock_ipo_min_shares} and {settings.stock_ipo_max_shares}",
        )
    if ipo_price < 1.0:
        raise HTTPException(status_code=400, detail="IPO price must be at least $1")
    if not 0.1 <= founder_keep_pct <= 0.7:
        raise HTTPException(
            status_code=400, detail="Founder must keep 10%–70% of shares"
        )

    taken = await db.execute(select(StockListing).where(StockListing.symbol == sym))
    if taken.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Symbol already taken")

    if character.cash < settings.stock_ipo_listing_fee:
        raise HTTPException(
            status_code=400,
            detail=f"Listing fee is ${settings.stock_ipo_listing_fee:.0f}",
        )

    founder_shares = int(total_shares * founder_keep_pct)
    float_shares = total_shares - founder_shares
    if float_shares < 100:
        raise HTTPException(status_code=400, detail="Public float too small")

    character.cash = round(character.cash - settings.stock_ipo_listing_fee, 2)
    now = utcnow()
    listing = StockListing(
        symbol=sym,
        name=business.name,
        issuer_type=StockIssuerType.BUSINESS,
        business_id=business.id,
        description=business.description or f"Shares in {business.name}",
        status=StockListingStatus.ACTIVE,
        share_price=round(ipo_price, 4),
        total_shares=total_shares,
        float_shares=float_shares,
        founder_shares=founder_shares,
        ipo_raised=0.0,
        listed_at=now,
        is_booming=business.cash_balance >= settings.stock_ipo_min_business_cash * 2,
    )
    db.add(listing)
    await db.flush()

    # Founder gets locked founder shares (can sell later on secondary market)
    holding = await _ensure_holding(db, character.id, listing.id)
    _add_shares(holding, founder_shares, ipo_price)

    business.is_public = True
    business.stock_listing_id = listing.id
    character.reputation += 10

    await news_service.publish(
        db,
        f"IPO: {sym} — {business.name}",
        f"{float_shares} shares offered at ${ipo_price:.2f}. "
        "Investors own shares; they exit only by selling. "
        "IPO proceeds fund the company — not a personal withdrawal.",
        category="economy",
        state_id=business.state_id,
    )
    await db.refresh(listing)
    return listing


async def buy_shares(
    db: AsyncSession, character: Character, listing_id: int, shares: int
) -> dict:
    """Buy from float (primary) or — if float empty — not available until someone sells.

    Primary: cash → issuer (business cash / gov). Secondary order book is sell-side only for MVP:
    buyers take from float first; peer sells use sell_shares.
    """
    ensure_can_act(character)
    if shares <= 0:
        raise HTTPException(status_code=400, detail="Shares must be positive")

    listing = await db.get(StockListing, listing_id)
    if listing is None or listing.status != StockListingStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.float_shares < shares:
        raise HTTPException(
            status_code=400,
            detail="Not enough float shares — wait for shareholders to sell",
        )

    settings = get_settings()
    price = listing.share_price
    gross = round(price * shares, 2)
    fee = round(gross * settings.stock_trade_fee_rate, 2)
    total = gross + fee
    if character.cash < total:
        raise HTTPException(
            status_code=400, detail=f"Need ${total:.2f} cash (incl. fee)"
        )

    character.cash = round(character.cash - total, 2)
    listing.float_shares -= shares

    # Primary capital goes to issuer — NOT withdrawable as "investor money" by owner personally
    if listing.issuer_type == StockIssuerType.BUSINESS and listing.business_id:
        business = await db.get(Business, listing.business_id)
        if business:
            business.cash_balance = round(business.cash_balance + gross, 2)
            listing.ipo_raised = round(listing.ipo_raised + gross, 2)
    elif listing.issuer_type == StockIssuerType.GOVERNMENT:
        nation = await politics_service.get_or_create_nation(db)
        # Park in notes tally / reputation of nation — use a soft treasury field via notes
        listing.ipo_raised = round(listing.ipo_raised + gross, 2)
        nation.notes = (
            f"Treasury raised ${listing.ipo_raised:.2f} via share sales"
        )

    holding = await _ensure_holding(db, character.id, listing.id)
    _add_shares(holding, shares, price)
    _bump_price(listing, shares, buying=True)

    db.add(
        StockTrade(
            listing_id=listing.id,
            buyer_id=character.id,
            seller_id=None,
            shares=shares,
            price_per_share=price,
            fee=fee,
            is_primary=True,
            posted_at=utcnow(),
        )
    )
    await db.flush()
    return {
        "symbol": listing.symbol,
        "shares": shares,
        "price_per_share": price,
        "fee": fee,
        "total_paid": total,
        "new_price": listing.share_price,
        "holding_shares": holding.shares,
        "note": "Primary purchase — capital funded the issuer. You exit only by selling shares.",
    }


async def sell_shares(
    db: AsyncSession, character: Character, listing_id: int, shares: int
) -> dict:
    """Secondary sale: market buyback from float expansion (company does NOT pay).

    For MVP without order book: exchange buys at current price into float
    (liquidity provider). Proceeds go to the selling shareholder only.
    Business cannot touch this payout.
    """
    ensure_can_act(character)
    if shares <= 0:
        raise HTTPException(status_code=400, detail="Shares must be positive")

    listing = await db.get(StockListing, listing_id)
    if listing is None or listing.status != StockListingStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Listing not found")

    holding = await _get_holding(db, character.id, listing_id)
    if holding is None or holding.shares < shares:
        raise HTTPException(status_code=400, detail="Not enough shares to sell")

    # Founder can sell founder shares; they become float
    settings = get_settings()
    price = listing.share_price
    gross = round(price * shares, 2)
    fee = round(gross * settings.stock_trade_fee_rate, 2)
    net = round(gross - fee, 2)

    _remove_shares(holding, shares)
    if listing.founder_shares > 0 and character.id:
        # Reduce tracked founder block if seller still looks like founder holding
        # (best-effort; shares are fungible after IPO)
        listing.founder_shares = max(0, listing.founder_shares - shares)

    listing.float_shares += shares
    character.cash = round(character.cash + net, 2)
    _bump_price(listing, shares, buying=False)

    db.add(
        StockTrade(
            listing_id=listing.id,
            buyer_id=None,
            seller_id=character.id,
            shares=shares,
            price_per_share=price,
            fee=fee,
            is_primary=False,
            posted_at=utcnow(),
        )
    )
    await db.flush()
    return {
        "symbol": listing.symbol,
        "shares": shares,
        "price_per_share": price,
        "fee": fee,
        "net_received": net,
        "new_price": listing.share_price,
        "holding_shares": holding.shares,
        "note": "Secondary sale — payout is yours. The business cannot reclaim share capital.",
    }


async def place_sell_order(
    db: AsyncSession,
    character: Character,
    listing_id: int,
    shares: int,
    price_each: float,
) -> dict:
    """Peer sell order — other players fill; company is not involved."""
    from app.models.social import StockSellOrder

    ensure_can_act(character)
    if shares <= 0 or price_each <= 0:
        raise HTTPException(status_code=400, detail="Invalid order")
    listing = await db.get(StockListing, listing_id)
    if listing is None or listing.status != StockListingStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Listing not found")
    holding = await _get_holding(db, character.id, listing_id)
    if holding is None or holding.shares < shares:
        raise HTTPException(status_code=400, detail="Not enough shares")
    _remove_shares(holding, shares)
    order = StockSellOrder(
        listing_id=listing_id,
        seller_id=character.id,
        shares=shares,
        price_each=round(price_each, 2),
        shares_remaining=shares,
        is_active=True,
    )
    db.add(order)
    await db.flush()
    return {
        "order_id": order.id,
        "symbol": listing.symbol,
        "shares": shares,
        "price_each": order.price_each,
    }


async def list_sell_orders(db: AsyncSession, listing_id: int | None = None) -> list[dict]:
    from app.models.social import StockSellOrder

    stmt = select(StockSellOrder).where(StockSellOrder.is_active.is_(True))
    if listing_id is not None:
        stmt = stmt.where(StockSellOrder.listing_id == listing_id)
    stmt = stmt.order_by(StockSellOrder.price_each.asc()).limit(100)
    result = await db.execute(stmt)
    rows = []
    for o in result.scalars().all():
        listing = await db.get(StockListing, o.listing_id)
        rows.append(
            {
                "order_id": o.id,
                "listing_id": o.listing_id,
                "symbol": listing.symbol if listing else None,
                "seller_id": o.seller_id,
                "shares_remaining": o.shares_remaining,
                "price_each": o.price_each,
            }
        )
    return rows


async def fill_sell_order(
    db: AsyncSession, character: Character, order_id: int, shares: int
) -> dict:
    from app.models.social import StockSellOrder
    from app.services import notify_service

    ensure_can_act(character)
    order = await db.get(StockSellOrder, order_id)
    if order is None or not order.is_active or order.shares_remaining <= 0:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.seller_id == character.id:
        raise HTTPException(status_code=400, detail="Cannot fill your own order")
    if shares <= 0 or shares > order.shares_remaining:
        raise HTTPException(status_code=400, detail="Invalid share amount")

    listing = await db.get(StockListing, order.listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    settings = get_settings()
    gross = round(order.price_each * shares, 2)
    fee = round(gross * settings.stock_trade_fee_rate, 2)
    total = round(gross + fee, 2)
    if character.cash < total:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    character.cash = round(character.cash - total, 2)
    seller = await db.get(Character, order.seller_id)
    if seller:
        seller.cash = round(seller.cash + gross, 2)
        await notify_service.push(
            db,
            seller.id,
            "Sell order filled",
            body=f"{shares} {listing.symbol} @ ${order.price_each:.2f}",
            category="stocks",
        )

    holding = await _get_holding(db, character.id, listing.id)
    if holding is None:
        holding = ShareHolding(
            character_id=character.id,
            listing_id=listing.id,
            shares=0,
            avg_cost=order.price_each,
        )
        db.add(holding)
        await db.flush()
    _add_shares(holding, shares, order.price_each)

    order.shares_remaining -= shares
    if order.shares_remaining <= 0:
        order.is_active = False

    db.add(
        StockTrade(
            listing_id=listing.id,
            buyer_id=character.id,
            seller_id=order.seller_id,
            shares=shares,
            price_per_share=order.price_each,
            fee=fee,
            is_primary=False,
            posted_at=utcnow(),
        )
    )
    await db.flush()
    return {
        "symbol": listing.symbol,
        "shares": shares,
        "price_each": order.price_each,
        "fee": fee,
        "total_paid": total,
        "cash": character.cash,
        "note": "Peer order fill — seller paid; company not involved.",
    }


async def seed_government_listings(db: AsyncSession) -> int:
    result = await db.execute(
        select(StockListing.id)
        .where(StockListing.issuer_type == StockIssuerType.GOVERNMENT)
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return 0

    now = utcnow()
    gov = [
        ("UATSY", "United Amir Treasury", 25.0, 50000, True),
        ("UANRL", "National Rail Corp", 18.0, 30000, True),
        ("UAEGY", "Amir Energy Board", 32.0, 40000, True),
        ("UAPRT", "Port Authority Bonds-Shares", 15.0, 20000, False),
    ]
    for symbol, name, price, shares, booming in gov:
        db.add(
            StockListing(
                symbol=symbol,
                name=name,
                issuer_type=StockIssuerType.GOVERNMENT,
                business_id=None,
                description=f"Government-backed listing: {name}",
                status=StockListingStatus.ACTIVE,
                share_price=price,
                total_shares=shares,
                float_shares=shares,
                founder_shares=0,
                ipo_raised=0.0,
                listed_at=now,
                is_booming=booming,
            )
        )
    await db.flush()
    return len(gov)
