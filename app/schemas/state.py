from pydantic import BaseModel, computed_field


class StateOut(BaseModel):
    id: int
    slug: str
    name: str
    capital: str
    economic_profile: str
    population_cap: int
    # Player-only home residents (cap / is_open)
    population_count: int
    npc_population_count: int = 0
    base_tax_rate: float
    permit_fee_multiplier: float
    crime_catch_rate: float
    average_income: float
    starting_bonus: float
    is_open: bool
    npc_mp_name: str | None
    mp_character_id: int | None

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def population_total(self) -> int:
        """Players + NPC citizens — what the world feels like."""
        return int(self.population_count) + int(self.npc_population_count or 0)


class StateSummaryOut(BaseModel):
    id: int
    slug: str
    name: str
    capital: str
    economic_profile: str
    # Kept as TOTAL for existing FE cards (players + NPCs)
    population_count: int
    population_cap: int
    npc_population_count: int = 0
    player_population: int = 0
    is_open: bool
    average_income: float
    starting_bonus: float
    crime_catch_rate: float

    model_config = {"from_attributes": True}


def state_summary(state) -> StateSummaryOut:
    players = int(state.population_count or 0)
    npcs = int(getattr(state, "npc_population_count", 0) or 0)
    return StateSummaryOut(
        id=state.id,
        slug=state.slug,
        name=state.name,
        capital=state.capital,
        economic_profile=state.economic_profile,
        population_count=players + npcs,
        population_cap=state.population_cap,
        npc_population_count=npcs,
        player_population=players,
        is_open=state.is_open,
        average_income=state.average_income,
        starting_bonus=state.starting_bonus,
        crime_catch_rate=state.crime_catch_rate,
    )


def state_detail(state) -> StateOut:
    return StateOut.model_validate(state)
