import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class EducationTrack(str, enum.Enum):
    SHORT_COURSE = "short_course"
    DIPLOMA = "diploma"
    BACHELORS = "bachelors"
    LAW = "law"
    MASTERS = "masters"
    MEDICAL = "medical"
    MILITARY_BASIC = "military_basic"


class EnrollmentStatus(str, enum.Enum):
    ENROLLED = "enrolled"
    COMPLETED = "completed"
    DROPPED = "dropped"
    FAILED = "failed"


# Real-time durations (days) and game age gain (years) — scaled activity table
EDUCATION_CATALOG: dict[EducationTrack, dict] = {
    EducationTrack.SHORT_COURSE: {
        "label": "Short course / certificate",
        "real_days": 1.5,
        "age_years": 0.5,
        "cost": 200,
        "level": 1,
    },
    EducationTrack.DIPLOMA: {
        "label": "Diploma",
        "real_days": 6,
        "age_years": 2.5,
        "cost": 800,
        "level": 2,
    },
    EducationTrack.BACHELORS: {
        "label": "Bachelor's degree",
        "real_days": 14,
        "age_years": 4.0,
        "cost": 2000,
        "level": 3,
    },
    EducationTrack.LAW: {
        "label": "Law school (LLB)",
        "real_days": 7,
        "age_years": 2.0,
        "cost": 2500,
        "level": 4,
    },
    EducationTrack.MASTERS: {
        "label": "Master's degree",
        "real_days": 7,
        "age_years": 2.0,
        "cost": 2200,
        "level": 4,
    },
    EducationTrack.MEDICAL: {
        "label": "Medical degree",
        "real_days": 21,
        "age_years": 6.0,
        "cost": 5000,
        "level": 5,
    },
    EducationTrack.MILITARY_BASIC: {
        "label": "Military basic training",
        "real_days": 2,
        "age_years": 0.5,
        "cost": 0,
        "level": 1,
    },
}


class EducationEnrollment(Base, TimestampMixin):
    __tablename__ = "education_enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    track: Mapped[EducationTrack] = mapped_column(Enum(EducationTrack))
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus), default=EnrollmentStatus.ENROLLED
    )
    title: Mapped[str] = mapped_column(String(128))
    cost_paid: Mapped[float] = mapped_column(Float)
    age_gain_years: Mapped[float] = mapped_column(Float)
    education_level: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id"), nullable=True
    )
