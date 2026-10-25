from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.character import Character
from app.models.item import ITEM_CATALOG, InventoryItem, MarketListing
from app.services.character_service import ensure_can_act
from app.services import notify_service


def shop_catalog() -> list[dict]:
    out = []
    for key, meta in ITEM_CATALOG.items():
        if meta.get("shop_price") is None:
            continue
        out.append(
            {
                "item_key": key,
                "name": meta["name"],
                "kind": meta["kind"].value if hasattr(meta["kind"], "value") else meta["kind"],
                "shop_price": meta["shop_price"],
                "description": meta["description"],
            }
        )
    return out


async def list_inventory(db: AsyncSession, character_id: int) -> list[dict]:
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.character_id == character_id,
            InventoryItem.quantity > 0,
        )
    )
    rows = []
    for item in result.scalars().all():
        meta = ITEM_CATALOG.get(item.item_key, {})
        rows.append(
            {
                "id": item.id,
                "item_key": item.item_key,
                "name": meta.get("name", item.item_key),
                "quantity": item.quantity,
                "kind": getattr(meta.get("kind"), "value", meta.get("kind")),
                "description": meta.get("description"),
                "effect": meta.get("effect"),
            }
        )
    return rows


async def _add_item(
    db: AsyncSession, character_id: int, item_key: str, qty: int = 1
) -> InventoryItem:
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.character_id == character_id,
            InventoryItem.item_key == item_key,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.quantity += qty
        await db.flush()
        return row
    row = InventoryItem(character_id=character_id, item_key=item_key, quantity=qty)
    db.add(row)
    await db.flush()
    return row


async def _take_item(
    db: AsyncSession, character_id: int, item_key: str, qty: int = 1
) -> InventoryItem:
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.character_id == character_id,
            InventoryItem.item_key == item_key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None or row.quantity < qty:
        raise HTTPException(status_code=400, detail="Not enough items")
    row.quantity -= qty
    await db.flush()
    return row


async def buy_from_shop(
    db: AsyncSession, character: Character, item_key: str, quantity: int = 1
) -> dict:
    ensure_can_act(character)
    meta = ITEM_CATALOG.get(item_key)
    if meta is None or meta.get("shop_price") is None:
        raise HTTPException(status_code=404, detail="Item not sold in shop")
    if quantity < 1 or quantity > 50:
        raise HTTPException(status_code=400, detail="Invalid quantity")
    total = meta["shop_price"] * quantity
    if character.cash < total:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    character.cash = round(character.cash - total, 2)
    await _add_item(db, character.id, item_key, quantity)
    await notify_service.push(
        db,
        character.id,
        f"Bought {quantity}× {meta['name']}",
        body=f"-${total:.2f}",
        category="inventory",
    )
    await db.flush()
    return {"item_key": item_key, "quantity": quantity, "spent": total, "cash": character.cash}


async def use_item(db: AsyncSession, character: Character, item_key: str) -> dict:
    ensure_can_act(character)
    meta = ITEM_CATALOG.get(item_key)
    if meta is None:
        raise HTTPException(status_code=404, detail="Unknown item")
    await _take_item(db, character.id, item_key, 1)
    effect = meta.get("effect", "")
    message = f"Used {meta['name']}"

    if effect == "heal_25":
        before = character.health
        character.health = min(character.max_health, character.health + 25)
        message = f"Healed {character.health - before} HP"
    elif effect == "energy_15":
        before = character.energy
        character.energy = min(character.max_energy, character.energy + 15)
        message = f"Restored {character.energy - before} energy"
    elif effect == "nerve_10":
        before = character.nerve
        character.nerve = min(character.max_nerve, character.nerve + 10)
        message = f"Restored {character.nerve - before} nerve"
    elif effect == "crime_boost_burglary":
        character.crime_boost_burglary = True
        message = "Lockpick ready for next burglary"
    elif effect and effect.startswith("fence_"):
        value = float(meta.get("fence_value", 0))
        character.cash = round(character.cash + value, 2)
        message = f"Fenced for ${value:.2f}"
    elif effect == "gym_bonus":
        # Permanent while owned — put it back
        await _add_item(db, character.id, item_key, 1)
        message = "Training weights equip passively while in inventory"

    await db.flush()
    return {
        "item_key": item_key,
        "message": message,
        "cash": character.cash,
        "energy": character.energy,
        "nerve": character.nerve,
        "health": character.health,
    }


async def list_market(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(MarketListing).where(MarketListing.is_active.is_(True)).order_by(MarketListing.id.desc()).limit(100)
    )
    rows = []
    for listing in result.scalars().all():
        meta = ITEM_CATALOG.get(listing.item_key, {})
        rows.append(
            {
                "id": listing.id,
                "seller_id": listing.seller_id,
                "item_key": listing.item_key,
                "name": meta.get("name", listing.item_key),
                "quantity": listing.quantity,
                "price_each": listing.price_each,
                "note": listing.note,
            }
        )
    return rows


async def list_on_market(
    db: AsyncSession,
    character: Character,
    item_key: str,
    quantity: int,
    price_each: float,
    note: str | None = None,
) -> MarketListing:
    ensure_can_act(character)
    if item_key not in ITEM_CATALOG:
        raise HTTPException(status_code=404, detail="Unknown item")
    if quantity < 1 or price_each <= 0:
        raise HTTPException(status_code=400, detail="Invalid listing")
    await _take_item(db, character.id, item_key, quantity)
    listing = MarketListing(
        seller_id=character.id,
        item_key=item_key,
        quantity=quantity,
        price_each=round(price_each, 2),
        is_active=True,
        note=note,
    )
    db.add(listing)
    await db.flush()
    await db.refresh(listing)
    return listing


async def buy_from_market(
    db: AsyncSession, character: Character, listing_id: int, quantity: int = 1
) -> dict:
    ensure_can_act(character)
    listing = await db.get(MarketListing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id == character.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own listing")
    if quantity < 1 or quantity > listing.quantity:
        raise HTTPException(status_code=400, detail="Invalid quantity")
    total = round(listing.price_each * quantity, 2)
    if character.cash < total:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    seller = await db.get(Character, listing.seller_id)
    character.cash = round(character.cash - total, 2)
    if seller:
        seller.cash = round(seller.cash + total, 2)
        await notify_service.push(
            db,
            seller.id,
            "Market sale",
            body=f"Sold {quantity}× {listing.item_key} for ${total:.2f}",
            category="market",
        )

    await _add_item(db, character.id, listing.item_key, quantity)
    listing.quantity -= quantity
    if listing.quantity <= 0:
        listing.is_active = False
    await db.flush()
    return {
        "listing_id": listing.id,
        "item_key": listing.item_key,
        "quantity": quantity,
        "spent": total,
        "cash": character.cash,
    }


async def grant_loot(
    db: AsyncSession, character_id: int, item_key: str, qty: int = 1
) -> None:
    if item_key in ITEM_CATALOG:
        await _add_item(db, character_id, item_key, qty)
