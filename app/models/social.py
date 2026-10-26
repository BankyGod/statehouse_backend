import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class RelationType(str, enum.Enum):
    FRIEND = "friend"
    ENEMY = "enemy"


class RelationStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"


class SocialRelation(Base, TimestampMixin):
    __tablename__ = "social_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    to_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[RelationType] = mapped_column(Enum(RelationType))
    status: Mapped[RelationStatus] = mapped_column(
        Enum(RelationStatus), default=RelationStatus.PENDING
    )


class AttackLog(Base, TimestampMixin):
    __tablename__ = "attack_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    attacker_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    defender_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    attacker_won: Mapped[bool] = mapped_column(Boolean)
    damage: Mapped[int] = mapped_column(Integer, default=0)
    cash_stolen: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(String(255))
    fought_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DirectMessage(Base, TimestampMixin):
    __tablename__ = "direct_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    to_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # Optional company sender (owner writing on behalf of the firm)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(128), nullable=True)
    body: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Faction(Base, TimestampMixin):
    __tablename__ = "factions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tag: Mapped[str] = mapped_column(String(8), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), index=True)
    treasury: Mapped[float] = mapped_column(Float, default=0.0)


class FactionMember(Base, TimestampMixin):
    __tablename__ = "faction_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    faction_id: Mapped[int] = mapped_column(
        ForeignKey("factions.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    rank: Mapped[str] = mapped_column(String(32), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorldEvent(Base, TimestampMixin):
    __tablename__ = "world_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    effect_key: Mapped[str] = mapped_column(String(64))  # e.g. job_pay_boost
    effect_value: Mapped[float] = mapped_column(Float, default=1.0)
    state_id: Mapped[int | None] = mapped_column(
        ForeignKey("states.id"), nullable=True, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StockSellOrder(Base, TimestampMixin):
    """Simple peer sell orders (MVP order book)."""

    __tablename__ = "stock_sell_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("stock_listings.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    shares: Mapped[int] = mapped_column(Integer)
    price_each: Mapped[float] = mapped_column(Float)
    shares_remaining: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
