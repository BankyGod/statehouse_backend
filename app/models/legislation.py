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


class BillStatus(str, enum.Enum):
    DEBATE = "debate"
    PASSED = "passed"
    FAILED = "failed"
    VETOED = "vetoed"
    ENACTED = "enacted"


class BillVoteChoice(str, enum.Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


class BudgetStatus(str, enum.Enum):
    OPEN = "open"
    PASSED = "passed"
    REJECTED = "rejected"


class Bill(Base, TimestampMixin):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    sponsor_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), index=True
    )
    sponsor_state_id: Mapped[int] = mapped_column(ForeignKey("states.id"))
    status: Mapped[BillStatus] = mapped_column(
        Enum(BillStatus), default=BillStatus.DEBATE
    )
    yes_votes: Mapped[int] = mapped_column(Integer, default=0)
    no_votes: Mapped[int] = mapped_column(Integer, default=0)
    abstain_votes: Mapped[int] = mapped_column(Integer, default=0)
    # NPC MPs auto-lean; stored so FE can show full house math
    npc_yes: Mapped[int] = mapped_column(Integer, default=0)
    npc_no: Mapped[int] = mapped_column(Integer, default=0)
    debate_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    vetoed: Mapped[bool] = mapped_column(Boolean, default=False)
    enacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BillVote(Base, TimestampMixin):
    __tablename__ = "bill_votes"
    __table_args__ = (
        UniqueConstraint("bill_id", "character_id", name="uq_bill_vote_mp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), index=True)
    choice: Mapped[BillVoteChoice] = mapped_column(Enum(BillVoteChoice))


class BudgetReading(Base, TimestampMixin):
    __tablename__ = "budget_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    national_tax_rate: Mapped[float] = mapped_column(Float, default=0.10)
    status: Mapped[BudgetStatus] = mapped_column(
        Enum(BudgetStatus), default=BudgetStatus.OPEN
    )
    yes_votes: Mapped[int] = mapped_column(Integer, default=0)
    no_votes: Mapped[int] = mapped_column(Integer, default=0)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BudgetVote(Base, TimestampMixin):
    __tablename__ = "budget_votes"
    __table_args__ = (
        UniqueConstraint("budget_id", "character_id", name="uq_budget_vote_mp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budget_readings.id"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), index=True)
    choice: Mapped[BillVoteChoice] = mapped_column(Enum(BillVoteChoice))


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    headline: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="general")
    state_id: Mapped[int | None] = mapped_column(
        ForeignKey("states.id"), nullable=True, index=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
