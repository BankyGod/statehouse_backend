"""Housing templates scaled by state income / capital pressure."""

from app.models.housing import HousingKind

# Multipliers applied to a state's average_income
HOUSING_TEMPLATES = [
    {
        "title": "Community hostel bed",
        "kind": HousingKind.HOSTEL,
        "description": "Shared bunk. Free for home-state residents; basic shelter.",
        "rent_factor": 0.0,
        "buy_price": None,
        "energy_bonus": 0,
        "home_state_only": True,
    },
    {
        "title": "Single room",
        "kind": HousingKind.ROOM,
        "description": "Small private room near the capital.",
        "rent_factor": 0.08,
        "buy_price": None,
        "energy_bonus": 5,
        "home_state_only": False,
    },
    {
        "title": "Studio apartment",
        "kind": HousingKind.APARTMENT,
        "description": "Compact apartment with a kitchenette.",
        "rent_factor": 0.15,
        "buy_price_factor": 18.0,
        "energy_bonus": 10,
        "home_state_only": False,
    },
    {
        "title": "Family house",
        "kind": HousingKind.HOUSE,
        "description": "Standalone house. Status property.",
        "rent_factor": 0.28,
        "buy_price_factor": 35.0,
        "energy_bonus": 20,
        "home_state_only": False,
    },
]
