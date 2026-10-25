import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ItemKind(str, enum.Enum):
    CONSUMABLE = "consumable"
    TOOL = "tool"
    LOOT = "loot"
    GEAR = "gear"


ITEM_CATALOG: dict[str, dict] = {
    "medkit": {
        "name": "Medkit",
        "kind": ItemKind.CONSUMABLE,
        "shop_price": 50.0,
        "description": "Restore 25 HP instantly.",
        "effect": "heal_25",
    },
    "energy_drink": {
        "name": "Energy drink",
        "kind": ItemKind.CONSUMABLE,
        "shop_price": 35.0,
        "description": "Restore 15 energy.",
        "effect": "energy_15",
    },
    "nerve_pill": {
        "name": "Nerve pill",
        "kind": ItemKind.CONSUMABLE,
        "shop_price": 40.0,
        "description": "Restore 10 nerve.",
        "effect": "nerve_10",
    },
    "lockpick": {
        "name": "Lockpick set",
        "kind": ItemKind.TOOL,
        "shop_price": 90.0,
        "description": "Slightly lowers catch chance on the next burglary.",
        "effect": "crime_boost_burglary",
    },
    "stolen_watch": {
        "name": "Stolen watch",
        "kind": ItemKind.LOOT,
        "shop_price": None,
        "description": "Fenceable loot from street crime.",
        "effect": "fence_80",
        "fence_value": 80.0,
    },
    "contraband": {
        "name": "Contraband crate",
        "kind": ItemKind.LOOT,
        "shop_price": None,
        "description": "High-value smuggled goods.",
        "effect": "fence_220",
        "fence_value": 220.0,
    },
    "training_weights": {
        "name": "Training weights",
        "kind": ItemKind.GEAR,
        "shop_price": 120.0,
        "description": "Permanent +5% gym gains while owned (one stack).",
        "effect": "gym_bonus",
    },
}


class InventoryItem(Base, TimestampMixin):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class MarketListing(Base, TimestampMixin):
    __tablename__ = "market_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_each: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Notification(Base, TimestampMixin):
    """Instant feed events (rent, payroll, attacks, etc.)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(32), default="general")
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
