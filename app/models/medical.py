import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class TreatmentType(str, enum.Enum):
    CLINIC = "clinic"
    HOSPITAL = "hospital"


class MedicalVisit(Base, TimestampMixin):
    __tablename__ = "medical_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    treatment_type: Mapped[TreatmentType] = mapped_column(Enum(TreatmentType))
    hp_before: Mapped[int] = mapped_column(Integer)
    hp_after: Mapped[int] = mapped_column(Integer)
    cost: Mapped[float] = mapped_column(Float)
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
