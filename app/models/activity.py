import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ActivityType(str, enum.Enum):
    EDUCATION = "education"
    JOB_SHIFT = "job_shift"
    BUSINESS = "business"
    TRAVEL = "travel"
    CRIME = "crime"
    MILITARY = "military"
    EXAM = "exam"
    OTHER = "other"


class ActivityStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Activity(Base, TimestampMixin):
    """Timed action queue — Torn-style wait timers."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    activity_type: Mapped[ActivityType] = mapped_column(Enum(ActivityType))
    status: Mapped[ActivityStatus] = mapped_column(
        Enum(ActivityStatus), default=ActivityStatus.IN_PROGRESS
    )
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Game-time age gained on completion (years)
    age_gain_years: Mapped[float] = mapped_column(Float, default=0.0)
    energy_cost: Mapped[int] = mapped_column(Integer, default=0)
    cash_delta: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
