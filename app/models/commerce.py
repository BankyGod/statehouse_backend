"""Company inventory & marketplace sales — sector commerce."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class BusinessInventoryItem(Base, TimestampMixin):
    __tablename__ = "business_inventory_items"
    __table_args__ = (
        UniqueConstraint("business_id", "sku", name="uq_biz_inv_sku"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)
    is_listed: Mapped[bool] = mapped_column(Boolean, default=True)


class BusinessSale(Base, TimestampMixin):
    """Ledger of product sales and service bookings."""

    __tablename__ = "business_sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    buyer_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # product | service
    sku: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    gross: Mapped[float] = mapped_column(Float)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    net_to_business: Mapped[float] = mapped_column(Float)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
