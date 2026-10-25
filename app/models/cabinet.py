import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Portfolio(str, enum.Enum):
    FINANCE = "finance"
    DEFENCE = "defence"
    HEALTH = "health"
    EDUCATION = "education"
    INTERIOR = "interior"
    TRADE = "trade"
    JUSTICE = "justice"
    AGRICULTURE = "agriculture"
    ENERGY = "energy"
    TRANSPORT = "transport"


PORTFOLIO_LABELS = {
    Portfolio.FINANCE: "Minister of Finance",
    Portfolio.DEFENCE: "Minister of Defence",
    Portfolio.HEALTH: "Minister of Health",
    Portfolio.EDUCATION: "Minister of Education",
    Portfolio.INTERIOR: "Minister of the Interior",
    Portfolio.TRADE: "Minister of Trade",
    Portfolio.JUSTICE: "Minister of Justice",
    Portfolio.AGRICULTURE: "Minister of Agriculture",
    Portfolio.ENERGY: "Minister of Energy",
    Portfolio.TRANSPORT: "Minister of Transport",
}


class CabinetSeat(Base, TimestampMixin):
    __tablename__ = "cabinet_seats"
    __table_args__ = (
        UniqueConstraint("portfolio", name="uq_cabinet_portfolio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio: Mapped[Portfolio] = mapped_column(Enum(Portfolio))
    title: Mapped[str] = mapped_column(String(128))
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True, index=True
    )
    npc_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_npc: Mapped[bool] = mapped_column(Boolean, default=True)
    appointed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_salary_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
