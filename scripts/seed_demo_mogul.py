"""Seed (or re-check) the demo mogul account. Safe to run while the API is up.

Usage:
  python scripts/seed_demo_mogul.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import Base, configure_engine, get_session_factory  # noqa: E402
from app.core.migrate import ensure_sqlite_columns  # noqa: E402
from app.core.config import get_settings  # noqa: E402
import app.models  # noqa: F401, E402
from app.seed import run_seed  # noqa: E402
from app.seed.demo_mogul import (  # noqa: E402
    DEMO_PASSWORD,
    DEMO_USERNAME,
    seed_demo_mogul,
)


async def main() -> None:
    settings = get_settings()
    engine = configure_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await ensure_sqlite_columns(conn)

    factory = get_session_factory()
    async with factory() as session:
        # Ensure base world exists first
        world = await run_seed(session)
        # run_seed already calls seed_mogul; print that result
        mogul = world.get("mogul") or await seed_demo_mogul(session)
        await session.commit()

    print("Demo mogul account")
    print(f"  username: {DEMO_USERNAME}")
    print(f"  password: {DEMO_PASSWORD}")
    print(f"  result:   {mogul}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
