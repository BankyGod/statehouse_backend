from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.core.config import get_settings
from app.core.database import Base, configure_engine, get_session_factory
from app.core.migrate import ensure_postgres_columns, ensure_sqlite_columns
from app.realtime.sio import sio
from app.seed import run_seed

# Import models so metadata is registered
import app.models  # noqa: F401

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.services import npc_sim_service

    engine = configure_engine()
    async with engine.begin() as conn:
        # Dev-friendly: create missing tables. Prefer `alembic upgrade head` in prod.
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await ensure_sqlite_columns(conn)
        elif "postgres" in settings.database_url:
            await ensure_postgres_columns(conn)
    factory = get_session_factory()
    async with factory() as session:
        seeded = await run_seed(session)
        await session.commit()
        print(f"Seed result: {seeded}")
    npc_sim_service.start_npc_sim_loop()
    yield
    await npc_sim_service.stop_npc_sim_loop()
    await engine.dispose()


fastapi_app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend for The State House: United Amir — a Torn-like text life sim "
        "with careers, business, crime, and optional politics. "
        "Realtime via Socket.IO at /socket.io"
    ),
    version=__version__,
    lifespan=lifespan,
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(api_router)


@fastapi_app.get("/health")
async def health():
    from sqlalchemy import text

    from app.core.database import get_session_factory

    db_ok = False
    db_error = None
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        db_error = str(exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "version": __version__,
        "game_time_ratio": settings.game_time_ratio,
        "realtime": "socket.io",
        "socket_path": "/socket.io",
        "database": {
            "ok": db_ok,
            "neon": settings.is_neon_postgres,
            "branch": settings.neon_branch,
            "error": db_error,
        },
        "neon_auth_configured": bool(
            settings.neon_auth_base_url and settings.neon_auth_jwks_url
        ),
        "npc_sim": settings.npc_sim_enabled,
    }


# Keep FastAPI app export for tests / OpenAPI
app = fastapi_app

# ASGI entry for uvicorn: wraps FastAPI + Socket.IO
asgi_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
