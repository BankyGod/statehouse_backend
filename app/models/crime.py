import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class CrimeType(str, enum.Enum):
    # Tier 1 — street
    STREET_THEFT = "street_theft"
    PICKPOCKET = "pickpocket"
    # Tier 2
    BURGLARY = "burglary"
    FENCING = "fencing"
    CAR_THEFT = "car_theft"
    # Tier 3
    FRAUD = "fraud"
    SMUGGLING = "smuggling"
    ARMED_ROBBERY = "armed_robbery"


# Tight security: high base catch rates; state multiplier applies on top
CRIME_CATALOG: dict[CrimeType, dict] = {
    CrimeType.STREET_THEFT: {
        "label": "Street theft",
        "tier": 1,
        "energy": 10,
        "nerve": 2,
        "min_payout": 20,
        "max_payout": 80,
        "heat_gain": 8,
        "base_catch_rate": 0.45,
        "jail_hours": 6,
        "fine": 100,
        "loot_chance": 0.15,
        "loot_item": "stolen_watch",
    },
    CrimeType.PICKPOCKET: {
        "label": "Pickpocket",
        "tier": 1,
        "energy": 8,
        "nerve": 1,
        "min_payout": 10,
        "max_payout": 50,
        "heat_gain": 5,
        "base_catch_rate": 0.40,
        "jail_hours": 4,
        "fine": 60,
        "loot_chance": 0.10,
        "loot_item": "stolen_watch",
    },
    CrimeType.BURGLARY: {
        "label": "Burglary",
        "tier": 2,
        "energy": 20,
        "nerve": 5,
        "min_payout": 80,
        "max_payout": 250,
        "heat_gain": 18,
        "base_catch_rate": 0.55,
        "jail_hours": 24,
        "fine": 400,
        "loot_chance": 0.25,
        "loot_item": "stolen_watch",
    },
    CrimeType.FENCING: {
        "label": "Fencing stolen goods",
        "tier": 2,
        "energy": 10,
        "nerve": 3,
        "min_payout": 40,
        "max_payout": 150,
        "heat_gain": 12,
        "base_catch_rate": 0.40,
        "jail_hours": 12,
        "fine": 250,
        "loot_chance": 0.0,
        "loot_item": None,
    },
    CrimeType.CAR_THEFT: {
        "label": "Car theft",
        "tier": 2,
        "energy": 22,
        "nerve": 6,
        "min_payout": 120,
        "max_payout": 350,
        "heat_gain": 20,
        "base_catch_rate": 0.58,
        "jail_hours": 30,
        "fine": 500,
        "loot_chance": 0.05,
        "loot_item": "contraband",
    },
    CrimeType.FRAUD: {
        "label": "Fraud",
        "tier": 3,
        "energy": 18,
        "nerve": 8,
        "min_payout": 100,
        "max_payout": 400,
        "heat_gain": 22,
        "base_catch_rate": 0.50,
        "jail_hours": 36,
        "fine": 600,
        "loot_chance": 0.0,
        "loot_item": None,
    },
    CrimeType.SMUGGLING: {
        "label": "Smuggling",
        "tier": 3,
        "energy": 28,
        "nerve": 10,
        "min_payout": 150,
        "max_payout": 600,
        "heat_gain": 28,
        "base_catch_rate": 0.60,
        "jail_hours": 48,
        "fine": 1000,
        "loot_chance": 0.30,
        "loot_item": "contraband",
    },
    CrimeType.ARMED_ROBBERY: {
        "label": "Armed robbery",
        "tier": 3,
        "energy": 35,
        "nerve": 14,
        "min_payout": 300,
        "max_payout": 900,
        "heat_gain": 40,
        "base_catch_rate": 0.70,
        "jail_hours": 72,
        "fine": 2000,
        "loot_chance": 0.20,
        "loot_item": "contraband",
    },
}


class CrimeAttempt(Base, TimestampMixin):
    __tablename__ = "crime_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    crime_type: Mapped[CrimeType] = mapped_column(Enum(CrimeType))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    caught: Mapped[bool] = mapped_column(Boolean)
    payout: Mapped[float] = mapped_column(Float, default=0.0)
    heat_applied: Mapped[float] = mapped_column(Float, default=0.0)
    fine_paid: Mapped[float] = mapped_column(Float, default=0.0)
    jail_hours: Mapped[int] = mapped_column(Integer, default=0)
    catch_chance_used: Mapped[float] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CriminalRecord(Base, TimestampMixin):
    __tablename__ = "criminal_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    crime_attempt_id: Mapped[int] = mapped_column(ForeignKey("crime_attempts.id"))
    charge: Mapped[str] = mapped_column(String(128))
    sentence_hours: Mapped[int] = mapped_column(Integer)
    fine: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
