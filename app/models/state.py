from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class State(Base, TimestampMixin):
    __tablename__ = "states"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    capital: Mapped[str] = mapped_column(String(128))
    economic_profile: Mapped[str] = mapped_column(Text)
    # Soft population management
    population_cap: Mapped[int] = mapped_column(Integer, default=500)
    # Real player home-state residents (used for is_open / cap)
    population_count: Mapped[int] = mapped_column(Integer, default=0)
    # Automated NPC citizens (display + sim; do not close states)
    npc_population_count: Mapped[int] = mapped_column(Integer, default=0)
    # Economy flavour knobs
    base_tax_rate: Mapped[float] = mapped_column(Float, default=0.08)
    permit_fee_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    crime_catch_rate: Mapped[float] = mapped_column(Float, default=0.35)
    average_income: Mapped[float] = mapped_column(Float, default=1200.0)
    starting_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    # NPC MP placeholder until a player wins
    npc_mp_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mp_character_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_mp_salary_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    characters: Mapped[list["Character"]] = relationship(  # noqa: F821
        back_populates="home_state",
        foreign_keys="Character.home_state_id",
    )
