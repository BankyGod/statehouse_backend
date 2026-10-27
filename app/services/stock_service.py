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


def _price_floor() -> float:
    return float(get_settings().stock_price_floor)


def _bump_price(listing: StockListing, shares: int, *, buying: bool) -> None:
    """Trade impact scaled by float scarcity (thin float → larger moves)."""
    settings = get_settings()
    float_left = max(int(listing.float_shares), 1)
    scarcity = min(3.0, max(0.35, shares / float_left * 8.0))
    impact = listing.share_price * settings.stock_price_impact * shares * scarcity
    if listing.is_booming:
        impact *= float(settings.stock_boom_impact_mult)
    floor = _price_floor()
    if buying:
        listing.share_price = round(listing.share_price + impact, 4)
    else:
        listing.share_price = round(max(floor, listing.share_price - impact), 4)


async def _bump_and_record(
    db: AsyncSession, listing: StockListing, shares: int, *, buying: bool
) -> None:
    from app.services import performance_service

    _bump_price(listing, shares, buying=buying)
    await performance_service.record_price_point(
        db, listing, reason="trade_buy" if buying else "trade_sell"
    )


async def _change_pct(db: AsyncSession, listing_id: int, current: float) -> float:
    """% change vs earliest price point in the last ~24h window (or prior point)."""
    from app.models.performance import StockPricePoint

    since = utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(StockPricePoint)
        .where(
            StockPricePoint.listing_id == listing_id,
            StockPricePoint.posted_at >= since,
        )
        .order_by(StockPricePoint.id.asc())
        .limit(1)
    )
    first = result.scalar_one_or_none()
    if first is None:
        result = await db.execute(
            select(StockPricePoint)
            .where(StockPricePoint.listing_id == listing_id)
            .order_by(StockPricePoint.id.desc())
            .offset(1)
            .limit(1)
        )
        first = result.scalar_one_or_none()
    if first is None or float(first.price) <= 0:
        return 0.0
    return round((float(current) - float(first.price)) / float(first.price) * 100.0, 2)


async def list_market(db: AsyncSession) -> list[dict]:
    """Active listings backed by a real business or state enterprise only."""
    await ensure_real_government_market(db)
    result = await db.execute(
        select(StockListing)
        .where(
            StockListing.status == StockListingStatus.ACTIVE,
            (StockListing.business_id.is_not(None))
            | (StockListing.enterprise_id.is_not(None)),
        )
        .order_by(StockListing.symbol)
    )
    out = []
    for L in result.scalars().all():
        issuer_name = L.name
        enterprise_slug = None
        if L.enterprise_id:
            from app.models.enterprise import StateEnterprise

            ent = await db.get(StateEnterprise, L.enterprise_id)
            if ent:
                issuer_name = ent.name
                enterprise_slug = ent.slug
        elif L.business_id:
            biz = await db.get(Business, L.business_id)
            if biz:
                issuer_name = biz.name
        change_pct = await _change_pct(db, L.id, L.share_price)
        out.append(
            {
                "id": L.id,
                "symbol": L.symbol,
                "name": L.name,
                "issuer_type": L.issuer_type.value,
                "issuer_name": issuer_name,
                "business_id": L.business_id,
                "enterprise_id": L.enterprise_id,
                "enterprise_slug": enterprise_slug,
                "description": L.description,
                "share_price": L.share_price,
                "change_pct": change_pct,
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

    from app.services import performance_service

    readiness = await performance_service.ipo_checklist(db, character, business)
    if not readiness["eligible"]:
        failed = [c["label"] for c in readiness["checks"] if not c["ok"]]
        raise HTTPException(
            status_code=400,
            detail="Not ready to list: " + "; ".join(failed[:4]),
        )

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
        is_booming=readiness["metrics"]["performance_score"] >= 70,
    )
    db.add(listing)
    await db.flush()

    # Founder gets locked founder shares (can sell later on secondary market)
    holding = await _ensure_holding(db, character.id, listing.id)
    _add_shares(holding, founder_shares, ipo_price)

    business.is_public = True
    business.stock_listing_id = listing.id
    character.reputation += 10
    await performance_service.record_price_point(db, listing, reason="ipo")
    await performance_service.record_snapshot(db, business)

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
        from app.models.treasury import TreasuryTxType
        from app.services import treasury_service

        listing.ipo_raised = round(listing.ipo_raised + gross, 2)
        await treasury_service.credit(
            db,
            gross,
            TreasuryTxType.FEE,
            note=f"SOE share sale — {listing.symbol}",
            character_id=character.id,
        )

    holding = await _ensure_holding(db, character.id, listing.id)
    _add_shares(holding, shares, price)
    await _bump_and_record(db, listing, shares, buying=True)

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
    await _bump_and_record(db, listing, shares, buying=False)

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

    # Peer fills move the quoted market toward the traded price
    listing.share_price = round(
        listing.share_price * 0.7 + order.price_each * 0.3,
        4,
    )
    listing.share_price = max(_price_floor(), listing.share_price)

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
    from app.services import performance_service

    await performance_service.record_price_point(db, listing, reason="order_fill")
    await db.flush()
    return {
        "symbol": listing.symbol,
        "shares": shares,
        "price_each": order.price_each,
        "fee": fee,
        "total_paid": total,
        "new_price": listing.share_price,
        "cash": character.cash,
        "note": "Peer order fill — seller paid; company not involved.",
    }


_gov_market_ready = False


async def seed_government_listings(db: AsyncSession) -> int:
    """Create/repair gov listings only for real StateEnterprises."""
    return await ensure_real_government_market(db, force=True)


async def ensure_real_government_market(
    db: AsyncSession, *, force: bool = False
) -> int:
    global _gov_market_ready
    if _gov_market_ready and not force:
        return 0
    """
    Ensure every SOE with a symbol has a linked listing at launch prices,
    delist orphan tickers (e.g. UATSY), hard-reprice once if still on old highs.
    """
    from sqlalchemy import delete

    from app.models.enterprise import StateEnterprise
    from app.models.performance import StockPricePoint
    from app.services import enterprise_service, performance_service

    await enterprise_service.ensure_enterprises_seeded(db)

    created = 0
    now = utcnow()
    launch = enterprise_service.GOV_LAUNCH_PRICES

    # Index enterprises by seed symbol
    symbol_to_ent: dict[str, StateEnterprise] = {}
    for slug, name, _k, _p, _s, symbol, desc in enterprise_service.ENTERPRISE_SEED:
        if not symbol:
            continue
        ent = (
            await db.execute(select(StateEnterprise).where(StateEnterprise.slug == slug))
        ).scalar_one_or_none()
        if ent is None:
            continue
        symbol_to_ent[symbol] = ent

        existing = (
            await db.execute(
                select(StockListing).where(StockListing.symbol == symbol)
            )
        ).scalar_one_or_none()
        price, shares = launch.get(symbol, (3.0, 20_000))
        if existing is None:
            listing = StockListing(
                symbol=symbol,
                name=name,
                issuer_type=StockIssuerType.GOVERNMENT,
                business_id=None,
                enterprise_id=ent.id,
                description=desc or f"State enterprise: {name}",
                status=StockListingStatus.ACTIVE,
                share_price=price,
                total_shares=shares,
                float_shares=shares,
                founder_shares=0,
                ipo_raised=0.0,
                listed_at=now,
                is_booming=False,
            )
            db.add(listing)
            await db.flush()
            ent.stock_listing_id = listing.id
            await performance_service.record_price_point(db, listing, reason="launch")
            created += 1
        else:
            existing.enterprise_id = ent.id
            existing.name = name
            existing.description = desc or existing.description
            existing.issuer_type = StockIssuerType.GOVERNMENT
            if existing.status == StockListingStatus.DELISTED:
                existing.status = StockListingStatus.ACTIVE
            ent.stock_listing_id = existing.id

    # Delist gov listings with no enterprise (UATSY etc.)
    orphans = (
        await db.execute(
            select(StockListing).where(
                StockListing.issuer_type == StockIssuerType.GOVERNMENT,
                StockListing.enterprise_id.is_(None),
            )
        )
    ).scalars().all()
    for L in orphans:
        # Might still be missing link — try symbol map
        ent = symbol_to_ent.get(L.symbol)
        if ent:
            L.enterprise_id = ent.id
            ent.stock_listing_id = L.id
            continue
        # Liquidate orphan holdings at last price so players aren't stuck
        if L.status != StockListingStatus.DELISTED:
            held_rows = (
                await db.execute(
                    select(ShareHolding).where(
                        ShareHolding.listing_id == L.id,
                        ShareHolding.shares > 0,
                    )
                )
            ).scalars().all()
            for h in held_rows:
                payout = round(h.shares * float(L.share_price), 2)
                ch = await db.get(Character, h.character_id)
                if ch and payout > 0:
                    ch.cash = round(ch.cash + payout, 2)
                h.shares = 0
                h.avg_cost = 0.0
            L.float_shares = L.total_shares
            L.status = StockListingStatus.DELISTED
    # Also force-delist UATSY by symbol if still active with a bad link
    uatsy_force = (
        await db.execute(select(StockListing).where(StockListing.symbol == "UATSY"))
    ).scalar_one_or_none()
    if uatsy_force and uatsy_force.status != StockListingStatus.DELISTED:
        held_rows = (
            await db.execute(
                select(ShareHolding).where(
                    ShareHolding.listing_id == uatsy_force.id,
                    ShareHolding.shares > 0,
                )
            )
        ).scalars().all()
        for h in held_rows:
            payout = round(h.shares * float(uatsy_force.share_price), 2)
            ch = await db.get(Character, h.character_id)
            if ch and payout > 0:
                ch.cash = round(ch.cash + payout, 2)
            h.shares = 0
            h.avg_cost = 0.0
        uatsy_force.float_shares = uatsy_force.total_shares
        uatsy_force.status = StockListingStatus.DELISTED
        uatsy_force.enterprise_id = None

    # Hard reprice if any linked gov listing is still above young-market band
    need_reprice = False
    for symbol, (price, _sh) in launch.items():
        L = (
            await db.execute(select(StockListing).where(StockListing.symbol == symbol))
        ).scalar_one_or_none()
        if L and L.share_price > price * 1.5:
            need_reprice = True
            break
    if need_reprice:
        for symbol, (price, shares) in launch.items():
            L = (
                await db.execute(
                    select(StockListing).where(StockListing.symbol == symbol)
                )
            ).scalar_one_or_none()
            if L is None:
                continue
            L.share_price = price
            L.total_shares = max(L.total_shares, shares)
            # Keep float as remaining unsold; if somehow oversold, clamp
            held = (
                await db.execute(
                    select(ShareHolding).where(ShareHolding.listing_id == L.id)
                )
            )
            sold = sum(h.shares for h in held.scalars().all())
            L.float_shares = max(0, L.total_shares - sold)
            L.is_booming = False
            await db.execute(
                delete(StockPricePoint).where(StockPricePoint.listing_id == L.id)
            )
            await performance_service.record_price_point(db, L, reason="launch_reprice")

    await db.flush()
    _gov_market_ready = True
    return created


def _apply_pct_move(listing: StockListing, pct: float) -> str:
    """Clamp and apply % move. Returns fund_up / fund_down / fund_flat."""
    settings = get_settings()
    sens = float(settings.stock_ops_price_sensitivity)
    pct = max(-sens, min(sens, pct))
    floor = _price_floor()
    if abs(pct) < 0.0005:
        return "fund_flat"
    old = listing.share_price
    listing.share_price = round(max(floor, old * (1.0 + pct)), 4)
    listing.is_booming = listing.share_price > old
    return "fund_up" if listing.share_price >= old else "fund_down"


async def _enterprise_fund_signal(
    db: AsyncSession, listing: StockListing
) -> float:
    """Signed raw signal from live activity (−1…+1-ish before clamp)."""
    from datetime import timedelta as td

    from app.models.education import EnrollmentStatus, EducationEnrollment
    from app.models.enterprise import EnterpriseKind, StateEnterprise
    from app.models.state import State
    from app.models.transport import TransportMode
    from app.models.travel import TravelLog
    from app.services import politics_service
    from sqlalchemy import func

    if not listing.enterprise_id:
        return 0.0
    ent = await db.get(StateEnterprise, listing.enterprise_id)
    if ent is None:
        return 0.0

    since = utcnow() - td(hours=6)
    signal = 0.0

    if ent.kind == EnterpriseKind.RAIL:
        cnt = await db.execute(
            select(func.count())
            .select_from(TravelLog)
            .where(
                TravelLog.mode == TransportMode.RAIL,
                TravelLog.created_at >= since,
            )
        )
        trips = int(cnt.scalar_one() or 0)
        # Busy rail → support; idle → mild pressure
        signal = (trips - 2) * 0.008

    elif ent.kind == EnterpriseKind.PORT:
        # Travel to/from port home state
        q = select(func.count()).select_from(TravelLog)
        if ent.home_state_id:
            q = q.where(
                TravelLog.created_at >= since,
                (TravelLog.to_state_id == ent.home_state_id)
                | (TravelLog.from_state_id == ent.home_state_id),
            )
        else:
            q = q.where(TravelLog.created_at >= since)
        trips = int((await db.execute(q)).scalar_one() or 0)
        signal = (trips - 3) * 0.007

    elif ent.kind == EnterpriseKind.POWER:
        pop = await db.execute(select(func.coalesce(func.sum(State.population_count), 0)))
        population = float(pop.scalar_one() or 0)
        nation = await politics_service.get_or_create_nation(db)
        treasury = float(nation.treasury_balance or 0)
        tax = float(nation.national_tax_rate or 0.05)
        # Healthy treasury + population demand supports energy board
        signal = 0.0
        signal += min(0.02, population / 500_000.0 * 0.015)
        if treasury < 20_000:
            signal -= 0.025
        elif treasury > 150_000:
            signal += 0.01
        # Very high tax can dampen industrial outlook
        if tax > 0.08:
            signal -= 0.015
        elif tax < 0.04:
            signal += 0.005

    elif ent.kind == EnterpriseKind.UNIVERSITY_SYSTEM:
        enr = await db.execute(
            select(func.count())
            .select_from(EducationEnrollment)
            .where(EducationEnrollment.status == EnrollmentStatus.ENROLLED)
        )
        students = int(enr.scalar_one() or 0)
        tuition = await db.execute(
            select(func.coalesce(func.sum(EducationEnrollment.cost_paid), 0.0)).where(
                EducationEnrollment.status == EnrollmentStatus.ENROLLED
            )
        )
        paid = float(tuition.scalar_one() or 0)
        signal = (students - 5) * 0.004 + min(0.02, paid / 50_000.0 * 0.02)

    # Thin float scarcity premium/discount
    if listing.total_shares > 0:
        float_ratio = listing.float_shares / max(listing.total_shares, 1)
        if float_ratio < 0.15:
            signal += 0.01  # scarce float
        elif float_ratio > 0.85:
            signal -= 0.005

    return signal


async def tick_enterprise_fundamentals(db: AsyncSession) -> dict:
    """World-tick price moves for SOE listings from real activity."""
    from app.services import performance_service

    await ensure_real_government_market(db)
    result = await db.execute(
        select(StockListing).where(
            StockListing.status == StockListingStatus.ACTIVE,
            StockListing.enterprise_id.is_not(None),
        )
    )
    moved = 0
    for listing in result.scalars().all():
        raw = await _enterprise_fund_signal(db, listing)
        reason = _apply_pct_move(listing, raw)
        await performance_service.record_price_point(db, listing, reason=reason)
        if reason != "fund_flat":
            moved += 1
    await db.flush()
    return {"listings": moved}


async def tick_public_business_ops(db: AsyncSession) -> int:
    """Run ops for owners of public companies so prices move without login."""
    from app.services import business_service

    result = await db.execute(
        select(Business).where(
            Business.is_public.is_(True),
            Business.status == BusinessStatus.ACTIVE,
        )
    )
    owners: set[int] = set()
    for biz in result.scalars().all():
        if biz.owner_id:
            owners.add(biz.owner_id)
    n = 0
    for oid in owners:
        ch = await db.get(Character, oid)
        if ch is None:
            continue
        await business_service.process_business_ops(db, ch)
        n += 1
    return n


async def apply_macro_news_shock(
    db: AsyncSession, *, category: str, headline: str
) -> int:
    """Small correlated nudge on SOE tickers from economy/politics news."""
    from app.models.enterprise import EnterpriseKind, StateEnterprise
    from app.services import performance_service

    cat = (category or "").lower()
    if cat not in ("economy", "politics"):
        return 0
    hl = (headline or "").lower()
    bump = 0.008 if cat == "economy" else 0.005
    if any(w in hl for w in ("crisis", "crash", "scandal", "deficit", "strike")):
        bump = -abs(bump) * 1.5
    elif any(w in hl for w in ("growth", "boom", "surplus", "passed", "reform")):
        bump = abs(bump)

    result = await db.execute(
        select(StockListing).where(
            StockListing.status == StockListingStatus.ACTIVE,
            StockListing.enterprise_id.is_not(None),
        )
    )
    n = 0
    for listing in result.scalars().all():
        ent = await db.get(StateEnterprise, listing.enterprise_id)
        if ent is None:
            continue
        local = bump
        # Sector tilt
        if ent.kind == EnterpriseKind.POWER and any(
            w in hl for w in ("energy", "tax", "power", "fuel")
        ):
            local *= 1.4
        if ent.kind in (EnterpriseKind.RAIL, EnterpriseKind.PORT) and any(
            w in hl for w in ("transport", "port", "rail", "travel")
        ):
            local *= 1.3
        if ent.kind == EnterpriseKind.UNIVERSITY_SYSTEM and any(
            w in hl for w in ("education", "university", "student")
        ):
            local *= 1.3
        reason = _apply_pct_move(listing, local)
        await performance_service.record_price_point(
            db, listing, reason=f"news_{reason}"
        )
        n += 1
    if n:
        await db.flush()
    return n


async def apply_budget_market_shock(db: AsyncSession, *, tax_rate: float) -> int:
    """Tax-rate change nudges energy/transport outlook."""
    from app.models.enterprise import EnterpriseKind, StateEnterprise
    from app.services import performance_service

    # Higher tax → slight industrial/pressure; lower → support
    base = (0.05 - float(tax_rate)) * 0.4  # ±0.02-ish at extremes
    result = await db.execute(
        select(StockListing).where(
            StockListing.status == StockListingStatus.ACTIVE,
            StockListing.enterprise_id.is_not(None),
        )
    )
    n = 0
    for listing in result.scalars().all():
        ent = await db.get(StateEnterprise, listing.enterprise_id)
        if ent is None:
            continue
        local = base
        if ent.kind == EnterpriseKind.POWER:
            local *= 1.5
        reason = _apply_pct_move(listing, local)
        await performance_service.record_price_point(
            db, listing, reason=f"budget_{reason}"
        )
        n += 1
    if n:
        await db.flush()
    return n
