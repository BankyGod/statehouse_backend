import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class StockIssuerType(str, enum.Enum):
    BUSINESS = "business"
    GOVERNMENT = "government"


class StockListingStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"


class StockTradeSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class StockListing(Base, TimestampMixin):
    """Public share listing. Shareholder money is NOT business operating cash after IPO."""

    __tablename__ = "stock_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    issuer_type: Mapped[StockIssuerType] = mapped_column(Enum(StockIssuerType))
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, unique=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[StockListingStatus] = mapped_column(
        Enum(StockListingStatus), default=StockListingStatus.ACTIVE
    )
    # Economics
    share_price: Mapped[float] = mapped_column(Float)
    total_shares: Mapped[int] = mapped_column(Integer)
    # Shares still held by issuer for primary sales (IPO leftover / treasury)
    float_shares: Mapped[int] = mapped_column(Integer)
    founder_shares: Mapped[int] = mapped_column(Integer, default=0)
    # IPO proceeds already paid into business/treasury — cannot be pulled as "shareholder cash"
    ipo_raised: Mapped[float] = mapped_column(Float, default=0.0)
    listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_booming: Mapped[bool] = mapped_column(Boolean, default=False)


class ShareHolding(Base, TimestampMixin):
    __tablename__ = "share_holdings"
    __table_args__ = (
        UniqueConstraint("character_id", "listing_id", name="uq_holding_char_listing"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("stock_listings.id"), index=True
    )
    shares: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)


class StockTrade(Base, TimestampMixin):
    __tablename__ = "stock_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("stock_listings.id"), index=True
    )
    buyer_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    seller_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    # seller_id null = primary/IPO or treasury sale
    shares: Mapped[int] = mapped_column(Integer)
    price_per_share: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
