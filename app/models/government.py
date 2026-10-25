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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class GovPostTier(str, enum.Enum):
    JUNIOR = "junior"
    OFFICER = "officer"
    SENIOR = "senior"
    DIRECTOR = "director"


class GovernmentPost(Base, TimestampMixin):
    """Civil-service / agency posts — NPC-filled until a player takes the seat."""

    __tablename__ = "government_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    agency: Mapped[str] = mapped_column(String(128))  # e.g. Ministry of Finance
    portfolio: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_id: Mapped[int | None] = mapped_column(
        ForeignKey("states.id"), nullable=True, index=True
    )
    tier: Mapped[GovPostTier] = mapped_column(Enum(GovPostTier))
    description: Mapped[str] = mapped_column(Text)
    wage_per_week: Mapped[float] = mapped_column(Float, default=200.0)
    min_education_level: Mapped[int] = mapped_column(Integer, default=1)
    min_reputation: Mapped[int] = mapped_column(Integer, default=0)
    requires_clean_record: Mapped[bool] = mapped_column(Boolean, default=True)

    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True, index=True
    )
    npc_name: Mapped[str] = mapped_column(String(128))
    is_npc: Mapped[bool] = mapped_column(Boolean, default=True)
    hired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_payday_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
