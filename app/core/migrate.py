"""Lightweight column adds for iterative MVP (SQLite + Postgres)."""

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
    "is_npc": "BOOLEAN DEFAULT 0",
    "npc_next_action_at": "DATETIME",
}

USER_COLUMNS = {
    "is_bot": "BOOLEAN DEFAULT 0",
}

STATE_COLUMNS = {
    "npc_population_count": "INTEGER DEFAULT 0",
}

BUSINESS_COLUMNS = {
    "is_public": "BOOLEAN DEFAULT 0",
    "stock_listing_id": "INTEGER",
    "last_ops_at": "DATETIME",
    "last_payroll_at": "DATETIME",
    "lifetime_revenue": "FLOAT DEFAULT 0",
    "lifetime_wages": "FLOAT DEFAULT 0",
    "entity_type": "VARCHAR(32) DEFAULT 'sole_trader'",
}


NATION_OFFICE_COLUMNS_SQLITE = {
    "vice_president_character_id": "INTEGER",
    "vice_president_npc_name": "VARCHAR(128) DEFAULT 'Vice President Kwesi Nkrumah (NPC)'",
    "speaker_npc_name": "VARCHAR(128) DEFAULT 'Speaker Ruth Mensah (NPC)'",
    "treasury_balance": "FLOAT DEFAULT 100000",
    "national_tax_rate": "FLOAT DEFAULT 0.05",
}

NATION_OFFICE_COLUMNS_PG = {
    "vice_president_character_id": "INTEGER",
    "vice_president_npc_name": "VARCHAR(128)",
    "speaker_npc_name": "VARCHAR(128)",
    "treasury_balance": "DOUBLE PRECISION DEFAULT 100000",
    "national_tax_rate": "DOUBLE PRECISION DEFAULT 0.05",
}

EDUCATION_ENROLLMENT_COLUMNS = {
    "institution_id": "INTEGER",
    "program_id": "INTEGER",
}

TRAVEL_LOG_COLUMNS_SQLITE = {
    "carrier_id": "INTEGER",
    "mode": "VARCHAR(16)",
    "carrier_name": "VARCHAR(128)",
}

TRAVEL_LOG_COLUMNS_PG = {
    "carrier_id": "INTEGER",
    "mode": "VARCHAR(16)",
    "carrier_name": "VARCHAR(128)",
}

HOUSING_LISTING_COLUMNS_SQLITE = {
    "ownership": "VARCHAR(32) DEFAULT 'government'",
    "owner_business_id": "INTEGER",
    "property_type_slug": "VARCHAR(32)",
    "offer_mode": "VARCHAR(16) DEFAULT 'both'",
    "acquisition_cost_each": "FLOAT DEFAULT 0",
    "units_total": "INTEGER",
    "units_available": "INTEGER",
    "happiness_bonus": "INTEGER DEFAULT 0",
    "energy_regen_bonus_minutes": "INTEGER DEFAULT 0",
}

HOUSING_LISTING_COLUMNS_PG = {
    "ownership": "VARCHAR(32) DEFAULT 'government'",
    "owner_business_id": "INTEGER",
    "property_type_slug": "VARCHAR(32)",
    "offer_mode": "VARCHAR(16) DEFAULT 'both'",
    "acquisition_cost_each": "DOUBLE PRECISION DEFAULT 0",
    "units_total": "INTEGER",
    "units_available": "INTEGER",
    "happiness_bonus": "INTEGER DEFAULT 0",
    "energy_regen_bonus_minutes": "INTEGER DEFAULT 0",
}

CHARACTER_HOUSING_BONUS_COLUMNS = {
    "happiness": "INTEGER DEFAULT 50",
    "housing_energy_regen_bonus": "INTEGER DEFAULT 0",
}

LOAN_COLUMNS_SQLITE = {
    "loan_kind": "VARCHAR(32) DEFAULT 'standard'",
    "auto_repay": "BOOLEAN DEFAULT 0",
    "repay_pct_of_gross": "FLOAT DEFAULT 0",
}

LOAN_COLUMNS_PG = {
    "loan_kind": "VARCHAR(32) DEFAULT 'standard'",
    "auto_repay": "BOOLEAN DEFAULT FALSE",
    "repay_pct_of_gross": "DOUBLE PRECISION DEFAULT 0",
}


async def _add_missing_sqlite(
    conn: AsyncConnection, table: str, columns: dict[str, str]
) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))


async def _add_missing_pg(
    conn: AsyncConnection, table: str, columns: dict[str, str]
) -> None:
    result = await conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    )
    existing = {row[0] for row in result.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
            )


async def ensure_sqlite_columns(conn: AsyncConnection) -> None:
    await _add_missing_sqlite(conn, "characters", CHARACTER_COLUMNS)
    await _add_missing_sqlite(conn, "users", USER_COLUMNS)
    await _add_missing_sqlite(conn, "states", STATE_COLUMNS)
    await _add_missing_sqlite(conn, "businesses", BUSINESS_COLUMNS)
    await _add_missing_sqlite(conn, "nation_office", NATION_OFFICE_COLUMNS_SQLITE)
    await _add_missing_sqlite(
        conn, "education_enrollments", EDUCATION_ENROLLMENT_COLUMNS
    )
    await _add_missing_sqlite(conn, "travel_logs", TRAVEL_LOG_COLUMNS_SQLITE)
    await _add_missing_sqlite(conn, "housing_listings", HOUSING_LISTING_COLUMNS_SQLITE)
    await _add_missing_sqlite(conn, "loans", LOAN_COLUMNS_SQLITE)
    await _add_missing_sqlite(conn, "characters", CHARACTER_HOUSING_BONUS_COLUMNS)
    await _add_missing_sqlite(
        conn,
        "direct_messages",
        {
            "business_id": "INTEGER",
            "subject": "VARCHAR(128)",
        },
    )


async def ensure_postgres_columns(conn: AsyncConnection) -> None:
    await _add_missing_pg(conn, "nation_office", NATION_OFFICE_COLUMNS_PG)
    await _add_missing_pg(
        conn,
        "characters",
        {
            "is_npc": "BOOLEAN DEFAULT FALSE",
            "npc_next_action_at": "TIMESTAMP WITH TIME ZONE",
        },
    )
    await _add_missing_pg(conn, "users", {"is_bot": "BOOLEAN DEFAULT FALSE"})
    await _add_missing_pg(
        conn, "states", {"npc_population_count": "INTEGER DEFAULT 0"}
    )
    await _add_missing_pg(
        conn, "education_enrollments", EDUCATION_ENROLLMENT_COLUMNS
    )
    await _add_missing_pg(conn, "travel_logs", TRAVEL_LOG_COLUMNS_PG)
    await _add_missing_pg(
        conn,
        "businesses",
        {"entity_type": "VARCHAR(32) DEFAULT 'sole_trader'"},
    )
    await _add_missing_pg(conn, "housing_listings", HOUSING_LISTING_COLUMNS_PG)
    await _add_missing_pg(conn, "loans", LOAN_COLUMNS_PG)
    await _add_missing_pg(conn, "characters", CHARACTER_HOUSING_BONUS_COLUMNS)
    await _add_missing_pg(
        conn,
        "direct_messages",
        {
            "business_id": "INTEGER",
            "subject": "VARCHAR(128)",
        },
    )
    # Backfill NPC office defaults if null
    await conn.execute(
        text(
            """
            UPDATE nation_office
            SET vice_president_npc_name = COALESCE(vice_president_npc_name, 'Vice President Kwesi Nkrumah (NPC)'),
                speaker_npc_name = COALESCE(speaker_npc_name, 'Speaker Ruth Mensah (NPC)'),
                president_npc_name = COALESCE(president_npc_name, 'President Ama Serwaa (NPC)'),
                treasury_balance = COALESCE(treasury_balance, 100000),
                national_tax_rate = COALESCE(national_tax_rate, 0.05)
            WHERE id = 1
            """
        )
    )
