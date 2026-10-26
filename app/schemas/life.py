from datetime import datetime

from pydantic import BaseModel, Field

from app.models.crime import CrimeType
from app.models.education import EducationTrack
from app.models.employee import EmployeeRole
from app.models.job import JobSector
from app.models.permit import PermitType


class EducationCatalogItem(BaseModel):
    track: EducationTrack
    label: str
    real_days: float
    age_years: float
    cost: float
    level: int


class EnrollRequest(BaseModel):
    """Prefer program_id. track kept for legacy clients."""

    program_id: int | None = None
    track: EducationTrack | None = None


class EnrollmentOut(BaseModel):
    id: int
    track: EducationTrack
    status: str
    title: str
    cost_paid: float
    age_gain_years: float
    education_level: int
    institution_id: int | None = None
    program_id: int | None = None
    institution_name: str | None = None
    institution_slug: str | None = None
    institution_kind: str | None = None
    institution_ownership: str | None = None
    started_at: datetime
    completes_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class JobListingOut(BaseModel):
    id: int
    state_id: int
    title: str
    sector: JobSector
    description: str
    wage_per_shift: float
    energy_cost: int
    shift_minutes: int
    min_education_level: int
    requires_clean_record: bool

    model_config = {"from_attributes": True}


class HireRequest(BaseModel):
    listing_id: int


class JobOut(BaseModel):
    id: int
    listing_id: int
    state_id: int
    hired_at: datetime
    shifts_completed: int
    is_active: bool

    model_config = {"from_attributes": True}


class BusinessCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    sector: str = Field(min_length=2, max_length=64)
    state_id: int
    local_address: str = Field(min_length=5, max_length=255)
    description: str | None = None
    entity_type: str = "sole_trader"
    starting_capital: float = Field(default=0, ge=0, le=50000)


class BusinessOut(BaseModel):
    id: int
    name: str
    sector: str
    entity_type: str = "sole_trader"
    state_id: int
    status: str
    cash_balance: float
    local_address: str
    is_home_state: bool
    registered_at: datetime | None
    registration_completes_at: datetime | None
    employee_count: int = 0
    description: str | None = None
    is_public: bool = False
    lifetime_revenue: float = 0.0
    lifetime_wages: float = 0.0

    model_config = {"from_attributes": True}


class HireNpcRequest(BaseModel):
    role: EmployeeRole = EmployeeRole.LABOURER
    display_name: str | None = Field(default=None, max_length=64)


class EmployeeOut(BaseModel):
    id: int
    business_id: int
    character_id: int | None
    display_name: str
    role: EmployeeRole
    wage_per_week: float
    is_npc: bool
    is_active: bool
    hired_at: datetime

    model_config = {"from_attributes": True}


class PermitApplyRequest(BaseModel):
    state_id: int
    permit_type: PermitType


class PermitOut(BaseModel):
    id: int
    state_id: int
    permit_type: PermitType
    status: str
    fee_paid: float
    issued_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class CrimeCatalogItem(BaseModel):
    crime_type: CrimeType
    label: str
    tier: int = 1
    energy: int
    nerve: int = 1
    min_payout: float
    max_payout: float
    heat_gain: float
    base_catch_rate: float
    jail_hours: int
    fine: float


class CrimeCommitRequest(BaseModel):
    crime_type: CrimeType


class CrimeResultOut(BaseModel):
    succeeded: bool
    caught: bool
    payout: float
    heat_applied: float
    fine_paid: float
    jail_hours: int
    catch_chance_used: float
    message: str
    character_cash: float
    character_heat: float
    is_jailed: bool
    health: int = 100
    is_hospitalized: bool = False
    injury: int = 0
    nerve: int = 0
    loot: str | None = None


class TravelQuoteRequest(BaseModel):
    to_state_id: int
    carrier_id: int | None = None


class TravelStartRequest(BaseModel):
    to_state_id: int
    carrier_id: int | None = None


class TravelQuoteOut(BaseModel):
    from_state_id: int
    to_state_id: int
    cost: float
    minutes: int
    discounted_cost: float | None = None
    carrier_id: int | None = None
    carrier_name: str | None = None
    mode: str | None = None
    permit_applies: bool | None = None


class BankAmountRequest(BaseModel):
    amount: float = Field(gt=0)


class BankMoveOut(BaseModel):
    cash: float
    bank_balance: float
    moved: float


class LoanCreateRequest(BaseModel):
    amount: float = Field(gt=0)


class LoanRepayRequest(BaseModel):
    amount: float = Field(gt=0)


class LoanOut(BaseModel):
    id: int
    principal: float
    remaining: float
    interest_rate: float
    status: str
    issued_at: datetime
    due_at: datetime
    payments_made: int

    model_config = {"from_attributes": True}


class BankSummaryOut(BaseModel):
    cash: float
    bank_balance: float
    savings_apr: float = 0.04
    transfer_fee: float = 5.0
    loans: list[LoanOut]


class BankTransferRequest(BaseModel):
    to_display_name: str = Field(min_length=3, max_length=64)
    amount: float = Field(gt=0)


class BankTxOut(BaseModel):
    id: int
    tx_type: str
    amount: float
    balance_after: float
    counterparty_id: int | None
    note: str | None
    posted_at: datetime

    model_config = {"from_attributes": True}


class StockIpoRequest(BaseModel):
    business_id: int
    symbol: str = Field(min_length=2, max_length=8)
    total_shares: int = Field(ge=1000, le=100000)
    ipo_price: float = Field(gt=0)
    founder_keep_pct: float = Field(default=0.4, ge=0.1, le=0.7)


class StockTradeRequest(BaseModel):
    listing_id: int
    shares: int = Field(gt=0)


class HousingListingOut(BaseModel):
    id: int
    state_id: int
    title: str
    kind: str
    description: str
    weekly_rent: float
    buy_price: float | None
    energy_bonus: int
    home_state_only: bool
    ownership: str = "government"
    owner_business_id: int | None = None
    property_type_slug: str | None = None
    offer_mode: str = "both"
    acquisition_cost_each: float = 0.0
    units_total: int | None = None
    units_available: int | None = None
    happiness_bonus: int = 0
    energy_regen_bonus_minutes: int = 0
    is_available: bool = True

    model_config = {"from_attributes": True}


class RealEstateListingCreate(BaseModel):
    property_type: str = Field(min_length=2, max_length=32)
    units: int = Field(default=1, ge=1, le=50)
    offer_mode: str = Field(default="both", pattern="^(rent|sale|both)$")
    title: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    weekly_rent: float | None = Field(default=None, ge=0)
    buy_price: float | None = Field(default=None, ge=0)


class RealEstateListingUpdate(BaseModel):
    weekly_rent: float | None = Field(default=None, ge=0)
    buy_price: float | None = None
    is_available: bool | None = None
    offer_mode: str | None = Field(default=None, pattern="^(rent|sale|both)$")


class HousingAssistRequest(BaseModel):
    listing_id: int | None = None


class ResidenceOut(BaseModel):
    id: int
    listing_id: int
    state_id: int
    tenure: str
    status: str
    weekly_rent: float
    rent_due_at: datetime | None
    missed_payments: int
    started_at: datetime

    model_config = {"from_attributes": True}


class HousingMoveRequest(BaseModel):
    listing_id: int


class ClinicHealRequest(BaseModel):
    hp_amount: int = Field(gt=0, le=100)


class CandidacyRegisterRequest(BaseModel):
    race_type: str = Field(pattern="^(mp|president)$")
    slogan: str = Field(min_length=2, max_length=160)


class VoteRequest(BaseModel):
    candidacy_id: int


class HealthStatusOut(BaseModel):
    health: int
    max_health: int
    is_hospitalized: bool
    hospital_until: datetime | None
    condition: str | None
    clinic_cost_per_hp: float
    hospital_base_hours: float
    seconds_remaining: int = 0


class BusinessCashRequest(BaseModel):
    amount: float = Field(gt=0)


class HirePlayerRequest(BaseModel):
    display_name: str = Field(min_length=3, max_length=64)
    role: EmployeeRole = EmployeeRole.CLERK
    wage_per_week: float | None = Field(default=None, gt=0)


class EmployeeUpdateRequest(BaseModel):
    role: EmployeeRole | None = None
    wage_per_week: float | None = Field(default=None, gt=0, le=5000)
    display_name: str | None = Field(default=None, min_length=2, max_length=64)


class GymTrainRequest(BaseModel):
    stat: str = Field(pattern="^(strength|defense|speed|dexterity)$")


class ShopBuyRequest(BaseModel):
    item_key: str
    quantity: int = Field(default=1, ge=1, le=50)


class MarketSellRequest(BaseModel):
    item_key: str
    quantity: int = Field(ge=1, le=50)
    price_each: float = Field(gt=0)
    note: str | None = Field(default=None, max_length=128)


class MarketBuyRequest(BaseModel):
    listing_id: int
    quantity: int = Field(default=1, ge=1, le=50)


class SocialNameRequest(BaseModel):
    display_name: str = Field(min_length=3, max_length=64)


class DmSendRequest(BaseModel):
    to_display_name: str = Field(min_length=3, max_length=64)
    body: str = Field(min_length=1, max_length=500)


class FactionCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    tag: str = Field(min_length=2, max_length=8)
    description: str | None = Field(default=None, max_length=500)


class StockOrderCreateRequest(BaseModel):
    listing_id: int
    shares: int = Field(gt=0)
    price_each: float = Field(gt=0)


class StockOrderFillRequest(BaseModel):
    order_id: int
    shares: int = Field(gt=0)
