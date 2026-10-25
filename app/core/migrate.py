"""Lightweight SQLite column adds for iterative MVP (no Alembic yet)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

CHARACTER_COLUMNS = {
    "last_energy_at": "DATETIME",
    "last_heat_tick_at": "DATETIME",
    "is_traveling": "BOOLEAN DEFAULT 0",
    "travel_until": "DATETIME",
    "travel_destination_id": "INTEGER",
    "is_homeless": "BOOLEAN DEFAULT 1",
    "active_residence_id": "INTEGER",
    "base_max_energy": "INTEGER DEFAULT 100",
    "health": "INTEGER DEFAULT 100",
    "max_health": "INTEGER DEFAULT 100",
    "last_health_at": "DATETIME",
    "is_hospitalized": "BOOLEAN DEFAULT 0",
    "hospital_until": "DATETIME",
    "condition": "VARCHAR(64)",
    "last_bank_interest_at": "DATETIME",
    "strength": "FLOAT DEFAULT 10",
    "defense": "FLOAT DEFAULT 10",
    "speed": "FLOAT DEFAULT 10",
    "dexterity": "FLOAT DEFAULT 10",
    "nerve": "INTEGER DEFAULT 20",
    "max_nerve": "INTEGER DEFAULT 20",
    "last_nerve_at": "DATETIME",
    "crime_boost_burglary": "BOOLEAN DEFAULT 0",
    "faction_id": "INTEGER",
}


BUSINESS_COLUMNS = {
    "is_public": "BOOLEAN DEFAULT 0",
    "stock_listing_id": "INTEGER",
    "last_ops_at": "DATETIME",
    "last_payroll_at": "DATETIME",
    "lifetime_revenue": "FLOAT DEFAULT 0",
    "lifetime_wages": "FLOAT DEFAULT 0",
}


async def _add_missing(conn: AsyncConnection, table: str, columns: dict[str, str]) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))


async def ensure_sqlite_columns(conn: AsyncConnection) -> None:
    await _add_missing(conn, "characters", CHARACTER_COLUMNS)
    await _add_missing(conn, "businesses", BUSINESS_COLUMNS)
