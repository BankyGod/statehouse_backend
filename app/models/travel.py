from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class TravelLog(Base, TimestampMixin):
    __tablename__ = "travel_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    from_state_id: Mapped[int] = mapped_column(ForeignKey("states.id"))
    to_state_id: Mapped[int] = mapped_column(ForeignKey("states.id"))
    cost: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id"), nullable=True
    )
