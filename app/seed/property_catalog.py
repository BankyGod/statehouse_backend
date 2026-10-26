"""Real-estate inventory types — company buys stock, then lists rent and/or sale."""

from app.models.housing import HousingKind

# acquisition_cost = what the company pays per unit from company cash to stock the listing.
# Tenants then pay weekly_rent / buy_price set by the company (suggested defaults below).
PROPERTY_TYPE_CATALOG: list[dict] = [
    {
        "slug": "bedsit",
        "label": "Bedsit / single room",
        "kind": HousingKind.ROOM.value,
        "blurb": "Compact private room. Entry-level rental stock.",
        "acquisition_cost": 6500.0,
        "suggested_weekly_rent": 40.0,
        "suggested_buy_price": 9500.0,
        "energy_bonus": 4,
        "happiness_bonus": 4,
        "energy_regen_bonus_minutes": 0,
    },
    {
        "slug": "studio",
        "label": "Studio apartment",
        "kind": HousingKind.APARTMENT.value,
        "blurb": "One open living space with kitchenette.",
        "acquisition_cost": 18000.0,
        "suggested_weekly_rent": 75.0,
        "suggested_buy_price": 28000.0,
        "energy_bonus": 8,
        "happiness_bonus": 10,
        "energy_regen_bonus_minutes": 0,
    },
    {
        "slug": "one_bed",
        "label": "1-bedroom apartment",
        "kind": HousingKind.APARTMENT.value,
        "blurb": "Separate bedroom — more comfort than a studio.",
        "acquisition_cost": 28000.0,
        "suggested_weekly_rent": 95.0,
        "suggested_buy_price": 42000.0,
        "energy_bonus": 12,
        "happiness_bonus": 16,
        "energy_regen_bonus_minutes": 1,
    },
    {
        "slug": "two_bed",
        "label": "2-bedroom apartment",
        "kind": HousingKind.APARTMENT.value,
        "blurb": "Family-ready flat; stronger quality-of-life bonuses.",
        "acquisition_cost": 40000.0,
        "suggested_weekly_rent": 130.0,
        "suggested_buy_price": 62000.0,
        "energy_bonus": 16,
        "happiness_bonus": 24,
        "energy_regen_bonus_minutes": 1,
    },
    {
        "slug": "family_house",
        "label": "Family house",
        "kind": HousingKind.HOUSE.value,
        "blurb": "Standalone house. Prestige living.",
        "acquisition_cost": 50000.0,
        "suggested_weekly_rent": 160.0,
        "suggested_buy_price": 78000.0,
        "energy_bonus": 22,
        "happiness_bonus": 35,
        "energy_regen_bonus_minutes": 2,
    },
    {
        "slug": "villa",
        "label": "Villa / estate",
        "kind": HousingKind.HOUSE.value,
        "blurb": "Top-tier home — max happiness and faster energy recovery.",
        "acquisition_cost": 120000.0,
        "suggested_weekly_rent": 280.0,
        "suggested_buy_price": 185000.0,
        "energy_bonus": 35,
        "happiness_bonus": 50,
        "energy_regen_bonus_minutes": 3,
    },
]


def property_type_by_slug(slug: str) -> dict | None:
    for row in PROPERTY_TYPE_CATALOG:
        if row["slug"] == slug:
            return row
    return None
