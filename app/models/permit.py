import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PermitType(str, enum.Enum):
    WORK = "work"
    BUSINESS = "business"
    TRAVEL = "travel"


class PermitStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DENIED = "denied"


class Permit(Base, TimestampMixin):
    __tablename__ = "permits"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    permit_type: Mapped[PermitType] = mapped_column(Enum(PermitType))
    status: Mapped[PermitStatus] = mapped_column(
        Enum(PermitStatus), default=PermitStatus.PENDING
    )
    fee_paid: Mapped[float] = mapped_column(Float, default=0.0)
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
