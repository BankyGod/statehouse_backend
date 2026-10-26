"""Travel carriers — air, rail, bus (gov + private)."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class TransportMode(str, enum.Enum):
    AIR = "air"
    RAIL = "rail"
    BUS = "bus"


class CarrierOwnership(str, enum.Enum):
    GOVERNMENT = "government"
    PRIVATE = "private"


class TransportCarrier(Base, TimestampMixin):
    __tablename__ = "transport_carriers"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    mode: Mapped[TransportMode] = mapped_column(Enum(TransportMode), index=True)
    ownership: Mapped[CarrierOwnership] = mapped_column(Enum(CarrierOwnership))
    enterprise_id: Mapped[int | None] = mapped_column(
        ForeignKey("state_enterprises.id"), nullable=True
    )
    base_fare_mult: Mapped[float] = mapped_column(Float, default=1.0)
    time_mult: Mapped[float] = mapped_column(Float, default=1.0)
    comfort: Mapped[int] = mapped_column(Integer, default=3)
    reliability: Mapped[int] = mapped_column(Integer, default=3)
    tagline: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
