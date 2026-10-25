from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.neon_db import to_async_sqlalchemy_url


class Base(DeclarativeBase):
    pass


engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def configure_engine(database_url: str | None = None, *, echo: bool | None = None) -> AsyncEngine:
    """Create (or recreate) the global async engine — used by app startup and tests."""
    global engine, AsyncSessionLocal
    settings = get_settings()
    url = database_url or settings.database_url
    if echo is None:
        echo = settings.app_env == "development"
    sqlalchemy_url, connect_args = to_async_sqlalchemy_url(url)
    engine = create_async_engine(
        sqlalchemy_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if AsyncSessionLocal is None:
        configure_engine()
    assert AsyncSessionLocal is not None
    return AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Default engine for normal app import
configure_engine()
