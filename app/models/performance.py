"""Company performance snapshots + stock price history (real ops-driven)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class BusinessPerformanceSnapshot(Base, TimestampMixin):
    __tablename__ = "business_performance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    cash_balance: Mapped[float] = mapped_column(Float)
    lifetime_revenue: Mapped[float] = mapped_column(Float)
    lifetime_wages: Mapped[float] = mapped_column(Float)
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    interval_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    interval_wages: Mapped[float] = mapped_column(Float, default=0.0)
    performance_score: Mapped[float] = mapped_column(Float, default=0.0)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StockPricePoint(Base, TimestampMixin):
    __tablename__ = "stock_price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("stock_listings.id", ondelete="CASCADE"), index=True
    )
    price: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(32), default="tick")
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
