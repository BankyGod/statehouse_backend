import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PartyIdeology(str, enum.Enum):
    CENTRIST = "centrist"
    LABOUR = "labour"
    BUSINESS = "business"
    NATIONALIST = "nationalist"
    GREEN = "green"


class PoliticalParty(Base, TimestampMixin):
    __tablename__ = "political_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    short_name: Mapped[str] = mapped_column(String(16), unique=True)
    slogan: Mapped[str] = mapped_column(String(160))
    ideology: Mapped[PartyIdeology] = mapped_column(Enum(PartyIdeology))
    description: Mapped[str] = mapped_column(Text)
    color_hex: Mapped[str] = mapped_column(String(7), default="#334155")
    npc_leader_name: Mapped[str] = mapped_column(String(128))
    leader_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    is_npc_led: Mapped[bool] = mapped_column(Boolean, default=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    # Soft count of NPC rank-and-file so the party feels populated
    npc_member_count: Mapped[int] = mapped_column(Integer, default=0)


class PartyMembership(Base, TimestampMixin):
    __tablename__ = "party_memberships"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_party_member_character"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int] = mapped_column(
        ForeignKey("political_parties.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[str] = mapped_column(String(32), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
