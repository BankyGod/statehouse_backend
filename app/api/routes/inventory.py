from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.life import MarketBuyRequest, MarketSellRequest, ShopBuyRequest
from app.services import character_service, inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/shop")
async def shop():
    return inventory_service.shop_catalog()


@router.get("/me")
async def my_inventory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await inventory_service.list_inventory(db, character.id)


@router.post("/shop/buy")
async def buy_shop(
    payload: ShopBuyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await inventory_service.buy_from_shop(
        db, character, payload.item_key, payload.quantity
    )


@router.post("/use/{item_key}")
async def use_item(
    item_key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await inventory_service.use_item(db, character, item_key)


@router.get("/market")
async def market(db: AsyncSession = Depends(get_db)):
    return await inventory_service.list_market(db)


@router.post("/market/sell", status_code=201)
async def market_sell(
    payload: MarketSellRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    listing = await inventory_service.list_on_market(
        db,
        character,
        payload.item_key,
        payload.quantity,
        payload.price_each,
        payload.note,
    )
    return {
        "id": listing.id,
        "item_key": listing.item_key,
        "quantity": listing.quantity,
        "price_each": listing.price_each,
    }


@router.post("/market/buy")
async def market_buy(
    payload: MarketBuyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await inventory_service.buy_from_market(
        db, character, payload.listing_id, payload.quantity
    )
