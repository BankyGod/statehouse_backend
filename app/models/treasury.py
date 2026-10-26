import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class TreasuryTxType(str, enum.Enum):
    INCOME_TAX = "income_tax"
    CORPORATE_TAX = "corporate_tax"
    FEE = "fee"
    FINE = "fine"
    BAIL = "bail"
    SALARY = "salary"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class TreasuryTransaction(Base, TimestampMixin):
    """Ledger for the United Amir national treasury bank account."""

    __tablename__ = "treasury_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tx_type: Mapped[TreasuryTxType] = mapped_column(Enum(TreasuryTxType), index=True)
    amount: Mapped[float] = mapped_column(Float)  # + credit, - debit
    balance_after: Mapped[float] = mapped_column(Float)
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True, index=True
    )
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
