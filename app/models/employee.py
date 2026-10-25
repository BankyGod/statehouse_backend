import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class EmployeeRole(str, enum.Enum):
    LABOURER = "labourer"
    CLERK = "clerk"
    SPECIALIST = "specialist"
    MANAGER = "manager"
    EXECUTIVE = "executive"


class BusinessEmployee(Base, TimestampMixin):
    __tablename__ = "business_employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    # Player employee (optional) or NPC name
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[EmployeeRole] = mapped_column(Enum(EmployeeRole))
    wage_per_week: Mapped[float] = mapped_column(Float, default=80.0)
    is_npc: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    hired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
