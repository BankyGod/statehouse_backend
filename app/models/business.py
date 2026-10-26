import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class BusinessStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class BusinessEntityType(str, enum.Enum):
    SOLE_TRADER = "sole_trader"
    PARTNERSHIP = "partnership"
    LIMITED_COMPANY = "limited_company"


class BusinessSector(str, enum.Enum):
    # Trade & services
    RETAIL = "retail"
    WHOLESALE = "wholesale"
    FOOD_BEVERAGE = "food_beverage"
    HOSPITALITY = "hospitality"
    PERSONAL_SERVICES = "personal_services"
    # Industry
    MANUFACTURING = "manufacturing"
    CONSTRUCTION = "construction"
    MINING = "mining"
    AGRICULTURE = "agriculture"
    ENERGY = "energy"
    # Transport & logistics
    TRUCKING = "trucking"
    SHIPPING = "shipping"
    WAREHOUSING = "warehousing"
    # Knowledge
    TECH = "tech"
    MEDIA = "media"
    PRIVATE_EDUCATION = "private_education"
    PRIVATE_HEALTHCARE = "private_healthcare"
    # Professional
    LEGAL = "legal"
    ACCOUNTING = "accounting"
    REAL_ESTATE = "real_estate"
    # Security
    PRIVATE_SECURITY = "private_security"
    # Catch-all
    OTHER = "other"


SECTOR_CATALOG: list[dict] = [
    {"value": BusinessSector.RETAIL, "label": "Retail", "group": "Trade & services"},
    {"value": BusinessSector.WHOLESALE, "label": "Wholesale", "group": "Trade & services"},
    {
        "value": BusinessSector.FOOD_BEVERAGE,
        "label": "Food & beverage",
        "group": "Trade & services",
    },
    {
        "value": BusinessSector.HOSPITALITY,
        "label": "Hospitality / hotels",
        "group": "Trade & services",
    },
    {
        "value": BusinessSector.PERSONAL_SERVICES,
        "label": "Personal services",
        "group": "Trade & services",
    },
    {
        "value": BusinessSector.MANUFACTURING,
        "label": "Manufacturing",
        "group": "Industry",
    },
    {
        "value": BusinessSector.CONSTRUCTION,
        "label": "Construction",
        "group": "Industry",
    },
    {"value": BusinessSector.MINING, "label": "Mining", "group": "Industry"},
    {
        "value": BusinessSector.AGRICULTURE,
        "label": "Agriculture / agribusiness",
        "group": "Industry",
    },
    {
        "value": BusinessSector.ENERGY,
        "label": "Energy / utilities (private)",
        "group": "Industry",
    },
    {
        "value": BusinessSector.TRUCKING,
        "label": "Trucking / haulage",
        "group": "Transport & logistics",
    },
    {
        "value": BusinessSector.SHIPPING,
        "label": "Shipping / freight",
        "group": "Transport & logistics",
    },
    {
        "value": BusinessSector.WAREHOUSING,
        "label": "Warehousing",
        "group": "Transport & logistics",
    },
    {"value": BusinessSector.TECH, "label": "Tech / software", "group": "Knowledge"},
    {
        "value": BusinessSector.MEDIA,
        "label": "Media / publishing",
        "group": "Knowledge",
    },
    {
        "value": BusinessSector.PRIVATE_EDUCATION,
        "label": "Education (private)",
        "group": "Knowledge",
    },
    {
        "value": BusinessSector.PRIVATE_HEALTHCARE,
        "label": "Healthcare (private clinic)",
        "group": "Knowledge",
    },
    {"value": BusinessSector.LEGAL, "label": "Legal practice", "group": "Professional"},
    {
        "value": BusinessSector.ACCOUNTING,
        "label": "Accounting / finance services",
        "group": "Professional",
    },
    {
        "value": BusinessSector.REAL_ESTATE,
        "label": "Real estate / property",
        "group": "Professional",
    },
    {
        "value": BusinessSector.PRIVATE_SECURITY,
        "label": "Private security",
        "group": "Security",
    },
    {"value": BusinessSector.OTHER, "label": "General / other", "group": "Other"},
]

ENTITY_TYPE_CATALOG: list[dict] = [
    {
        "value": BusinessEntityType.SOLE_TRADER,
        "label": "Sole trader",
        "registration_fee": 100.0,
        "blurb": "You alone - cheapest registration.",
    },
    {
        "value": BusinessEntityType.PARTNERSHIP,
        "label": "Partnership",
        "registration_fee": 150.0,
        "blurb": "Shared ownership; standard fee.",
    },
    {
        "value": BusinessEntityType.LIMITED_COMPANY,
        "label": "Limited company",
        "registration_fee": 250.0,
        "blurb": "Separate legal entity; best for later IPO.",
    },
]


class Business(Base, TimestampMixin):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    sector: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(
        String(32), default=BusinessEntityType.SOLE_TRADER.value
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BusinessStatus] = mapped_column(
        Enum(BusinessStatus), default=BusinessStatus.PENDING
    )
    cash_balance: Mapped[float] = mapped_column(Float, default=0.0)
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registration_completes_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    local_address: Mapped[str] = mapped_column(String(255))
    is_home_state: Mapped[bool] = mapped_column(Boolean, default=True)
    # Set when listed on the exchange — owner cannot siphon shareholder capital
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_listing_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_ops_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_payroll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lifetime_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_wages: Mapped[float] = mapped_column(Float, default=0.0)
