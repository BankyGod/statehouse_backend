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


class HousingKind(str, enum.Enum):
    HOSTEL = "hostel"
    ROOM = "room"
    APARTMENT = "apartment"
    HOUSE = "house"


class TenureType(str, enum.Enum):
    RENT = "rent"
    OWN = "own"


class ResidenceStatus(str, enum.Enum):
    ACTIVE = "active"
    EVICTED = "evicted"
    SOLD = "sold"
    LEFT = "left"


class HousingListing(Base, TimestampMixin):
    __tablename__ = "housing_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    kind: Mapped[HousingKind] = mapped_column(Enum(HousingKind))
    description: Mapped[str] = mapped_column(Text)
    weekly_rent: Mapped[float] = mapped_column(Float, default=0.0)
    buy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_bonus: Mapped[int] = mapped_column(Integer, default=0)
    home_state_only: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)


class Residence(Base, TimestampMixin):
    __tablename__ = "residences"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[int] = mapped_column(ForeignKey("housing_listings.id"))
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    tenure: Mapped[TenureType] = mapped_column(Enum(TenureType))
    status: Mapped[ResidenceStatus] = mapped_column(
        Enum(ResidenceStatus), default=ResidenceStatus.ACTIVE
    )
    weekly_rent: Mapped[float] = mapped_column(Float, default=0.0)
    rent_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    missed_payments: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
