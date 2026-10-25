import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import Base, configure_engine, get_session_factory
from app.seed import run_seed
import app.models  # noqa: F401


@pytest.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()

    engine = configure_engine(echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        await run_seed(session)
        await session.commit()

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "player@test.com",
            "username": "player1",
            "password": "password123",
        },
    )
    login = await client.post(
        "/api/auth/login",
        data={"username": "player1", "password": "password123"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def character(client: AsyncClient, auth_headers: dict[str, str]) -> dict:
    states = (await client.get("/api/states")).json()
    nf = next(s for s in states if s["slug"] == "new-frontier")
    resp = await client.post(
        "/api/characters",
        headers=auth_headers,
        json={"display_name": "TestHero", "home_state_id": nf["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
