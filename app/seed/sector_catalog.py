"""Playable goods & services per business sector — real money loops for players."""

from __future__ import annotations

# Products: owner restocks/produces into inventory; customers buy.
# kind: restock (buy wholesale into stock) | produce (spend cash to make)
SECTOR_PRODUCTS: dict[str, list[dict]] = {
    "retail": [
        {
            "sku": "staples",
            "label": "Household staples",
            "kind": "restock",
            "unit_cost": 6.0,
            "default_price": 12.0,
            "effects": {"energy": 5, "happiness": 2},
        },
        {
            "sku": "gadgets",
            "label": "Gadgets",
            "kind": "restock",
            "unit_cost": 18.0,
            "default_price": 32.0,
            "effects": {"happiness": 4},
        },
        {
            "sku": "apparel",
            "label": "Apparel",
            "kind": "restock",
            "unit_cost": 10.0,
            "default_price": 22.0,
            "effects": {"happiness": 3, "reputation": 1},
        },
    ],
    "wholesale": [
        {
            "sku": "bulk_food",
            "label": "Bulk food crates",
            "kind": "restock",
            "unit_cost": 40.0,
            "default_price": 55.0,
            "b2b": True,
        },
        {
            "sku": "bulk_parts",
            "label": "Industrial parts",
            "kind": "restock",
            "unit_cost": 60.0,
            "default_price": 85.0,
            "b2b": True,
        },
    ],
    "food_beverage": [
        {
            "sku": "meals",
            "label": "Prepared meals",
            "kind": "produce",
            "unit_cost": 4.0,
            "default_price": 11.0,
            "effects": {"energy": 20, "happiness": 4},
        },
        {
            "sku": "drinks",
            "label": "Drinks pack",
            "kind": "produce",
            "unit_cost": 2.0,
            "default_price": 6.0,
            "effects": {"energy": 8},
        },
    ],
    "manufacturing": [
        {
            "sku": "finished_goods",
            "label": "Finished goods",
            "kind": "produce",
            "unit_cost": 8.0,
            "default_price": 16.0,
            "b2b": True,
        },
        {
            "sku": "components",
            "label": "Components",
            "kind": "produce",
            "unit_cost": 5.0,
            "default_price": 9.0,
            "b2b": True,
        },
    ],
    "mining": [
        {
            "sku": "ore",
            "label": "Ore loads",
            "kind": "produce",
            "unit_cost": 12.0,
            "default_price": 20.0,
            "b2b": True,
        },
    ],
    "agriculture": [
        {
            "sku": "crops",
            "label": "Crop harvest",
            "kind": "produce",
            "unit_cost": 3.0,
            "default_price": 8.0,
            "effects": {"energy": 6},
            "b2b": True,
        },
        {
            "sku": "livestock",
            "label": "Livestock lot",
            "kind": "produce",
            "unit_cost": 15.0,
            "default_price": 28.0,
            "b2b": True,
        },
    ],
    "warehousing": [
        {
            "sku": "storage_slot",
            "label": "Storage slot-day",
            "kind": "produce",
            "unit_cost": 1.0,
            "default_price": 4.0,
            "b2b": True,
        },
    ],
    "tech": [
        {
            "sku": "software_license",
            "label": "Software license",
            "kind": "produce",
            "unit_cost": 5.0,
            "default_price": 25.0,
            "effects": {"reputation": 1},
        },
        {
            "sku": "device",
            "label": "Device kit",
            "kind": "restock",
            "unit_cost": 30.0,
            "default_price": 55.0,
            "effects": {"happiness": 5},
        },
    ],
    "media": [
        {
            "sku": "ad_slot",
            "label": "Ad slot",
            "kind": "produce",
            "unit_cost": 2.0,
            "default_price": 20.0,
            "effects": {"reputation": 2},
            "b2b": True,
        },
        {
            "sku": "print_run",
            "label": "Print / stream pack",
            "kind": "produce",
            "unit_cost": 3.0,
            "default_price": 9.0,
            "effects": {"happiness": 2},
        },
    ],
    "telecom": [
        {
            "sku": "sim_kit",
            "label": "SIM / handset kit",
            "kind": "restock",
            "unit_cost": 8.0,
            "default_price": 22.0,
            "effects": {"happiness": 3},
        },
    ],
    "other": [
        {
            "sku": "general_goods",
            "label": "General goods",
            "kind": "restock",
            "unit_cost": 5.0,
            "default_price": 10.0,
            "effects": {"energy": 3},
        },
        {
            "sku": "fuel_can",
            "label": "Fuel can",
            "kind": "restock",
            "unit_cost": 7.0,
            "default_price": 16.0,
            "effects": {"fuel_days": 3},
        },
    ],
}

# Services: customers book; company earns price - unit_cost (opex).
# effects applied on book: heal, energy, heat_cut, reputation, education_bump, crime_protect_hours
SECTOR_SERVICES: dict[str, list[dict]] = {
    "hospitality": [
        {
            "sku": "room_night",
            "label": "Hotel room night",
            "unit_cost": 8.0,
            "default_price": 45.0,
            "effects": {"energy": 25, "happiness": 5},
        },
        {
            "sku": "day_pass",
            "label": "Day lounge pass",
            "unit_cost": 3.0,
            "default_price": 15.0,
            "effects": {"energy": 10},
        },
    ],
    "personal_services": [
        {
            "sku": "grooming",
            "label": "Grooming / salon",
            "unit_cost": 2.0,
            "default_price": 18.0,
            "effects": {"happiness": 8, "reputation": 1},
        },
        {
            "sku": "laundry",
            "label": "Laundry service",
            "unit_cost": 1.0,
            "default_price": 8.0,
            "effects": {"happiness": 3},
        },
    ],
    "construction": [
        {
            "sku": "repair_crew",
            "label": "Building repair crew",
            "unit_cost": 40.0,
            "default_price": 120.0,
            "effects": {"happiness": 5},
        },
        {
            "sku": "fit_out",
            "label": "Interior fit-out",
            "unit_cost": 80.0,
            "default_price": 220.0,
            "effects": {"happiness": 10},
        },
    ],
    "energy": [
        {
            "sku": "power_pack",
            "label": "Private power pack (7d)",
            "unit_cost": 10.0,
            "default_price": 35.0,
            "effects": {"energy": 15, "power_days": 7},
        },
        {
            "sku": "fuel_contract",
            "label": "Fuel top-up (3d travel discount)",
            "unit_cost": 8.0,
            "default_price": 28.0,
            "effects": {"fuel_days": 3, "energy": 5},
        },
    ],
    "insurance": [
        {
            "sku": "health_cover",
            "label": "Health cover (7d)",
            "unit_cost": 12.0,
            "default_price": 55.0,
            "effects": {"heal": 15, "insure_days": 7},
        },
        {
            "sku": "travel_cover",
            "label": "Travel cover (7d)",
            "unit_cost": 8.0,
            "default_price": 40.0,
            "effects": {"insure_days": 7, "fuel_days": 2},
        },
    ],
    "telecom": [
        {
            "sku": "data_plan",
            "label": "Data / voice plan (7d)",
            "unit_cost": 5.0,
            "default_price": 25.0,
            "effects": {"happiness": 4, "reputation": 1},
        },
    ],
    "trucking": [
        {
            "sku": "local_haul",
            "label": "Local haul contract",
            "unit_cost": 15.0,
            "default_price": 55.0,
            "effects": {},
        },
        {
            "sku": "interstate_haul",
            "label": "Interstate haul",
            "unit_cost": 35.0,
            "default_price": 110.0,
            "effects": {},
        },
    ],
    "shipping": [
        {
            "sku": "coastal_freight",
            "label": "Coastal freight slot",
            "unit_cost": 50.0,
            "default_price": 160.0,
            "effects": {},
        },
    ],
    "private_education": [
        {
            "sku": "short_course",
            "label": "Private short course",
            "unit_cost": 20.0,
            "default_price": 90.0,
            "effects": {"education_bump": 1, "age_years": 0.05},
        },
    ],
    "private_healthcare": [
        {
            "sku": "clinic_visit",
            "label": "Clinic visit",
            "unit_cost": 15.0,
            "default_price": 75.0,
            "effects": {"heal": 30},
        },
        {
            "sku": "checkup",
            "label": "Full checkup",
            "unit_cost": 25.0,
            "default_price": 120.0,
            "effects": {"heal": 50, "happiness": 5},
        },
    ],
    "legal": [
        {
            "sku": "legal_brief",
            "label": "Legal consultation",
            "unit_cost": 20.0,
            "default_price": 95.0,
            "effects": {"heat_cut": 5, "reputation": 2},
        },
    ],
    "accounting": [
        {
            "sku": "books_review",
            "label": "Books & tax review",
            "unit_cost": 15.0,
            "default_price": 70.0,
            "effects": {"reputation": 1},
        },
    ],
    "private_security": [
        {
            "sku": "guard_week",
            "label": "Guard detail (7d)",
            "unit_cost": 40.0,
            "default_price": 140.0,
            "effects": {"crime_protect_hours": 168},
        },
    ],
}


def products_for(sector: str) -> list[dict]:
    return list(SECTOR_PRODUCTS.get(sector, SECTOR_PRODUCTS.get("other", [])))


def services_for(sector: str) -> list[dict]:
    return list(SECTOR_SERVICES.get(sector, []))


def sector_mode(sector: str) -> str:
    if sector == "real_estate":
        return "real_estate"
    if sector in SECTOR_SERVICES and sector not in SECTOR_PRODUCTS:
        return "services"
    if sector in SECTOR_PRODUCTS and sector not in SECTOR_SERVICES:
        return "inventory"
    if sector in SECTOR_SERVICES and sector in SECTOR_PRODUCTS:
        return "mixed"
    return "inventory"


def all_playable_sectors() -> list[str]:
    return sorted(set(SECTOR_PRODUCTS) | set(SECTOR_SERVICES) | {"real_estate"})
