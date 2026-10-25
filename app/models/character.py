from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Character(Base, TimestampMixin):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    home_state_id: Mapped[int] = mapped_column(
        ForeignKey("states.id"), index=True
    )
    # Mutable after first 3 real days only (enforced in service)
    home_state_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    home_state_chosen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    age_years: Mapped[float] = mapped_column(Float, default=18.0)
    cash: Mapped[float] = mapped_column(Float, default=500.0)
    bank_balance: Mapped[float] = mapped_column(Float, default=0.0)
    last_bank_interest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    energy: Mapped[int] = mapped_column(Integer, default=100)
    max_energy: Mapped[int] = mapped_column(Integer, default=100)
    last_energy_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heat_tick_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    heat: Mapped[float] = mapped_column(Float, default=0.0)
    is_jailed: Mapped[bool] = mapped_column(Boolean, default=False)
    jail_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_traveling: Mapped[bool] = mapped_column(Boolean, default=False)
    travel_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    travel_destination_id: Mapped[int | None] = mapped_column(
        ForeignKey("states.id"), nullable=True
    )
    current_state_id: Mapped[int] = mapped_column(
        ForeignKey("states.id"), index=True
    )
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    criminal_record_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Housing
    is_homeless: Mapped[bool] = mapped_column(Boolean, default=True)
    active_residence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_max_energy: Mapped[int] = mapped_column(Integer, default=100)
    # Health
    health: Mapped[int] = mapped_column(Integer, default=100)
    max_health: Mapped[int] = mapped_column(Integer, default=100)
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_hospitalized: Mapped[bool] = mapped_column(Boolean, default=False)
    hospital_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Gym / combat stats
    strength: Mapped[float] = mapped_column(Float, default=10.0)
    defense: Mapped[float] = mapped_column(Float, default=10.0)
    speed: Mapped[float] = mapped_column(Float, default=10.0)
    dexterity: Mapped[float] = mapped_column(Float, default=10.0)

    # Crime nerve (separate from energy)
    nerve: Mapped[int] = mapped_column(Integer, default=20)
    max_nerve: Mapped[int] = mapped_column(Integer, default=20)
    last_nerve_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # One-shot burglary catch reduction from lockpick
    crime_boost_burglary: Mapped[bool] = mapped_column(Boolean, default=False)

    # Faction
    faction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Automated citizens (same rules as players; driven by npc_sim_service)
    is_npc: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    npc_next_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="character")  # noqa: F821
    home_state: Mapped["State"] = relationship(  # noqa: F821
        foreign_keys=[home_state_id],
        back_populates="characters",
    )
    current_state: Mapped["State"] = relationship(foreign_keys=[current_state_id])  # noqa: F821
