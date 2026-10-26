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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ElectionStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    CAMPAIGN = "campaign"
    VOTING = "voting"
    CLOSED = "closed"


class RaceType(str, enum.Enum):
    MP = "mp"
    PRESIDENT = "president"


class Election(Base, TimestampMixin):
    __tablename__ = "elections"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    status: Mapped[ElectionStatus] = mapped_column(
        Enum(ElectionStatus), default=ElectionStatus.CAMPAIGN
    )
    campaign_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    voting_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    voting_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    term_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Candidacy(Base, TimestampMixin):
    __tablename__ = "candidacies"
    __table_args__ = (
        UniqueConstraint(
            "election_id",
            "character_id",
            "race_type",
            name="uq_candidacy_char_race",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("elections.id"), index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    race_type: Mapped[RaceType] = mapped_column(Enum(RaceType))
    # MP races are per home state; president has state_id null
    state_id: Mapped[int | None] = mapped_column(
        ForeignKey("states.id"), nullable=True, index=True
    )
    slogan: Mapped[str] = mapped_column(String(160))
    vote_count: Mapped[int] = mapped_column(Integer, default=0)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False)


class Ballot(Base, TimestampMixin):
    """One vote per character per race per election."""

    __tablename__ = "ballots"
    __table_args__ = (
        UniqueConstraint(
            "election_id",
            "voter_id",
            "race_type",
            name="uq_ballot_voter_race",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("elections.id"), index=True)
    voter_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    race_type: Mapped[RaceType] = mapped_column(Enum(RaceType))
    candidacy_id: Mapped[int] = mapped_column(ForeignKey("candidacies.id"))
    state_id: Mapped[int | None] = mapped_column(ForeignKey("states.id"), nullable=True)


class NationOffice(Base, TimestampMixin):
    """Singleton row id=1 for national offices."""

    __tablename__ = "nation_office"

    id: Mapped[int] = mapped_column(primary_key=True)
    president_character_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    president_npc_name: Mapped[str] = mapped_column(
        String(128), default="President Ama Serwaa (NPC)"
    )
    vice_president_character_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    vice_president_npc_name: Mapped[str] = mapped_column(
        String(128), default="Vice President Kwesi Nkrumah (NPC)"
    )
    speaker_character_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speaker_npc_name: Mapped[str] = mapped_column(
        String(128), default="Speaker Ruth Mensah (NPC)"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # National treasury bank account (all taxes & gov fees)
    treasury_balance: Mapped[float] = mapped_column(Float, default=100_000.0)
    # Active rate from last passed budget reading
    national_tax_rate: Mapped[float] = mapped_column(Float, default=0.05)
