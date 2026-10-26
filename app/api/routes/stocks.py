from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import (
    StockIpoRequest,
    StockOrderCreateRequest,
    StockOrderFillRequest,
    StockTradeRequest,
)
from app.services import character_service, performance_service, stock_service

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/market")
async def market(db: AsyncSession = Depends(get_db)):
    return {"listings": await stock_service.list_market(db)}


@router.get("/listings/{listing_id}/history")
async def listing_history(
    listing_id: int,
    limit: int = Query(default=120, ge=10, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Real share-price ticks from trades and company ops."""
    points = await performance_service.listing_price_history(db, listing_id, limit=limit)
    return {"listing_id": listing_id, "points": points}


@router.get("/portfolio")
async def portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {"holdings": await stock_service.my_portfolio(db, character)}


@router.post("/ipo", status_code=201)
async def ipo(
    payload: StockIpoRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    listing = await stock_service.ipo_business(
        db,
        character,
        payload.business_id,
        symbol=payload.symbol,
        total_shares=payload.total_shares,
        ipo_price=payload.ipo_price,
        founder_keep_pct=payload.founder_keep_pct,
    )
    return {
        "id": listing.id,
        "symbol": listing.symbol,
        "share_price": listing.share_price,
        "float_shares": listing.float_shares,
        "founder_shares": listing.founder_shares,
        "is_booming": listing.is_booming,
    }


@router.post("/buy")
async def buy(
    payload: StockTradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await stock_service.buy_shares(
        db, character, payload.listing_id, payload.shares
    )


@router.post("/sell")
async def sell(
    payload: StockTradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await stock_service.sell_shares(
        db, character, payload.listing_id, payload.shares
    )


@router.get("/orders")
async def sell_orders(
    listing_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return {"orders": await stock_service.list_sell_orders(db, listing_id)}


@router.post("/orders", status_code=201)
async def place_order(
    payload: StockOrderCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await stock_service.place_sell_order(
        db, character, payload.listing_id, payload.shares, payload.price_each
    )


@router.post("/orders/fill")
async def fill_order(
    payload: StockOrderFillRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await stock_service.fill_sell_order(
        db, character, payload.order_id, payload.shares
    )
