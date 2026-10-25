from pydantic import BaseModel


class StateOut(BaseModel):
    id: int
    slug: str
    name: str
    capital: str
    economic_profile: str
    population_cap: int
    population_count: int
    base_tax_rate: float
    permit_fee_multiplier: float
    crime_catch_rate: float
    average_income: float
    starting_bonus: float
    is_open: bool
    npc_mp_name: str | None
    mp_character_id: int | None

    model_config = {"from_attributes": True}


class StateSummaryOut(BaseModel):
    id: int
    slug: str
    name: str
    capital: str
    economic_profile: str
    population_count: int
    population_cap: int
    is_open: bool
    average_income: float
    starting_bonus: float
    crime_catch_rate: float

    model_config = {"from_attributes": True}
