"""Seed automated NPC citizens into every state."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, configure_engine, get_session_factory
from app.core.migrate import ensure_postgres_columns, ensure_sqlite_columns
from app.core.config import get_settings
import app.models  # noqa: F401
from app.services import npc_sim_service


async def main() -> None:
    settings = get_settings()
    engine = configure_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await ensure_sqlite_columns(conn)
        elif "postgres" in settings.database_url:
            await ensure_postgres_columns(conn)

    factory = get_session_factory()
    async with factory() as db:
        result = await npc_sim_service.ensure_npc_citizens(db)
        print(result)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
