"""Thin state-owned enterprises (ports, rail, power, public university system)."""

from __future__ import annotations

import enum

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class EnterpriseKind(str, enum.Enum):
    PORT = "port"
    RAIL = "rail"
    AIR = "air"
    BUS = "bus"
    POWER = "power"
    UNIVERSITY_SYSTEM = "university_system"


class EnterprisePortfolio(str, enum.Enum):
    TRANSPORT = "transport"
    ENERGY = "energy"
    EDUCATION = "education"
    FINANCE = "finance"


class StateEnterprise(Base, TimestampMixin):
    __tablename__ = "state_enterprises"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[EnterpriseKind] = mapped_column(Enum(EnterpriseKind), index=True)
    portfolio: Mapped[EnterprisePortfolio] = mapped_column(Enum(EnterprisePortfolio))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_state_id: Mapped[int | None] = mapped_column(
        ForeignKey("states.id"), nullable=True
    )
    stock_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_listings.id"), nullable=True
    )
    # Operating ledger (travel fares, tuition, grid fees, etc.)
    cash_balance: Mapped[float] = mapped_column(Float, default=50_000.0)
    lifetime_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_costs: Mapped[float] = mapped_column(Float, default=0.0)
    last_ops_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
