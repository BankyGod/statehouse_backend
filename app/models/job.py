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


class JobSector(str, enum.Enum):
    GOVERNMENT = "government"
    HEALTH = "health"
    EDUCATION = "education"
    FARMING = "farming"
    MINING = "mining"
    TRADE = "trade"
    LOGISTICS = "logistics"
    HOSPITALITY = "hospitality"
    SECURITY = "security"
    MEDIA = "media"
    ENERGY = "energy"
    TECH = "tech"
    LEGAL = "legal"
    MILITARY = "military"
    OTHER = "other"


class JobListing(Base, TimestampMixin):
    __tablename__ = "job_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    sector: Mapped[JobSector] = mapped_column(Enum(JobSector))
    description: Mapped[str] = mapped_column(Text)
    wage_per_shift: Mapped[float] = mapped_column(Float)
    energy_cost: Mapped[int] = mapped_column(Integer, default=10)
    # Real minutes for one shift (Torn-like short loops)
    shift_minutes: Mapped[int] = mapped_column(Integer, default=60)
    min_education_level: Mapped[int] = mapped_column(Integer, default=0)
    requires_clean_record: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(Base, TimestampMixin):
    """Character's current employment."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"))
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"))
    hired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shifts_completed: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
