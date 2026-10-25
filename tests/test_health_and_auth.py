import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["game_time_ratio"] == 8


@pytest.mark.asyncio
async def test_register_login_me(client: AsyncClient):
    reg = await client.post(
        "/api/auth/register",
        json={
            "email": "a@test.com",
            "username": "alice",
            "password": "password123",
        },
    )
    assert reg.status_code == 201
    assert reg.json()["username"] == "alice"

    login = await client.post(
        "/api/auth/login",
        data={"username": "alice", "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "a@test.com"
