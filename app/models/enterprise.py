"""Thin state-owned enterprises (ports, rail, power, public university system)."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class EnterpriseKind(str, enum.Enum):
    PORT = "port"
    RAIL = "rail"
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
