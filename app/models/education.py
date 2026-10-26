import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
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


class InstitutionKind(str, enum.Enum):
    PUBLIC_UNIVERSITY = "public_university"
    PRIVATE_UNIVERSITY = "private_university"
    POLYTECHNIC = "polytechnic"
    MILITARY_ACADEMY = "military_academy"
    MEDICAL_SCHOOL = "medical_school"


class InstitutionOwnership(str, enum.Enum):
    GOVERNMENT = "government"
    PRIVATE = "private"


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


class EducationInstitution(Base, TimestampMixin):
    __tablename__ = "education_institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[InstitutionKind] = mapped_column(Enum(InstitutionKind), index=True)
    ownership: Mapped[InstitutionOwnership] = mapped_column(Enum(InstitutionOwnership))
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    enterprise_id: Mapped[int | None] = mapped_column(
        ForeignKey("state_enterprises.id"), nullable=True
    )
    prestige: Mapped[int] = mapped_column(Integer, default=3)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


class EducationProgram(Base, TimestampMixin):
    __tablename__ = "education_programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("education_institutions.id", ondelete="CASCADE"), index=True
    )
    track: Mapped[EducationTrack] = mapped_column(Enum(EducationTrack), index=True)
    title: Mapped[str] = mapped_column(String(128))
    real_days: Mapped[float] = mapped_column(Float)
    age_years: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float)
    level: Mapped[int] = mapped_column(Integer)
    min_education_level: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class EducationEnrollment(Base, TimestampMixin):
    __tablename__ = "education_enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    track: Mapped[EducationTrack] = mapped_column(Enum(EducationTrack))
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("education_institutions.id"), nullable=True, index=True
    )
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("education_programs.id"), nullable=True, index=True
    )
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
