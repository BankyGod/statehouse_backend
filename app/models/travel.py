from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin
from app.models.transport import TransportMode


class TravelLog(Base, TimestampMixin):
    __tablename__ = "travel_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    from_state_id: Mapped[int] = mapped_column(ForeignKey("states.id"))
    to_state_id: Mapped[int] = mapped_column(ForeignKey("states.id"))
    cost: Mapped[float] = mapped_column(Float)
    carrier_id: Mapped[int | None] = mapped_column(
        ForeignKey("transport_carriers.id"), nullable=True, index=True
    )
    mode: Mapped[TransportMode | None] = mapped_column(
        Enum(TransportMode), nullable=True
    )
    carrier_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id"), nullable=True
    )
