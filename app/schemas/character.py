from datetime import datetime

from pydantic import BaseModel, Field


class CharacterCreate(BaseModel):
    display_name: str = Field(min_length=3, max_length=64)
    home_state_id: int
    bio: str | None = Field(default=None, max_length=500)


class CharacterOut(BaseModel):
    id: int
    display_name: str
    home_state_id: int
    current_state_id: int
    home_state_locked: bool
    home_state_chosen_at: datetime
    age_years: float
    cash: float
    bank_balance: float
    energy: int
    max_energy: int
    reputation: int
    heat: float
    is_jailed: bool
    jail_until: datetime | None
    is_traveling: bool
    travel_until: datetime | None
    travel_destination_id: int | None
    is_homeless: bool
    active_residence_id: int | None
    health: int
    max_health: int
    is_hospitalized: bool
    hospital_until: datetime | None
    condition: str | None
    bio: str | None
    criminal_record_summary: str | None
    strength: float = 10.0
    defense: float = 10.0
    speed: float = 10.0
    dexterity: float = 10.0
    nerve: int = 20
    max_nerve: int = 20
    faction_id: int | None = None
    is_npc: bool = False

    model_config = {"from_attributes": True}


class HomeStateResetRequest(BaseModel):
    new_home_state_id: int
