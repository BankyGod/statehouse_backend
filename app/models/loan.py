import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class LoanStatus(str, enum.Enum):
    ACTIVE = "active"
    PAID = "paid"
    DEFAULTED = "defaulted"


class LoanKind(str, enum.Enum):
    STANDARD = "standard"
    HOUSING_WELFARE = "housing_welfare"


class Loan(Base, TimestampMixin):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    principal: Mapped[float] = mapped_column(Float)
    remaining: Mapped[float] = mapped_column(Float)
    interest_rate: Mapped[float] = mapped_column(Float)
    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus), default=LoanStatus.ACTIVE
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payments_made: Mapped[int] = mapped_column(Integer, default=0)
    loan_kind: Mapped[str] = mapped_column(
        String(32), default=LoanKind.STANDARD.value, index=True
    )
    auto_repay: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fraction of each taxable paycheck garnished toward remaining
    repay_pct_of_gross: Mapped[float] = mapped_column(Float, default=0.0)
