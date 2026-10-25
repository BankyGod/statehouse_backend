import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_twenty_states_seeded(client: AsyncClient):
    resp = await client.get("/api/states")
    assert resp.status_code == 200
    states = resp.json()
    assert len(states) == 20
    assert any(s["slug"] == "new-frontier" for s in states)


@pytest.mark.asyncio
async def test_character_job_and_chat(
    client: AsyncClient, auth_headers: dict, character: dict
):
    assert character["display_name"] == "TestHero"
    assert character["is_homeless"] is False
    assert character["cash"] >= 500

    me = await client.get("/api/characters/me", headers=auth_headers)
    assert me.status_code == 200
    assert "health" in me.json()
    assert "energy" in me.json()

    listings = await client.get("/api/jobs/listings", headers=auth_headers)
    assert listings.status_code == 200
    jobs = listings.json()
    assert len(jobs) >= 1

    hire = await client.post(
        "/api/jobs/hire",
        headers=auth_headers,
        json={"listing_id": jobs[0]["id"]},
    )
    assert hire.status_code == 201

    work = await client.post("/api/jobs/work", headers=auth_headers)
    assert work.status_code == 200
    assert work.json()["wage"] > 0
    assert work.json()["energy"] < character["energy"]

    state_id = character["home_state_id"]
    chat = await client.post(
        f"/api/chat/states/{state_id}/messages",
        headers=auth_headers,
        json={"body": "Hello United Amir"},
    )
    assert chat.status_code == 201

    msgs = await client.get("/api/chat/home/messages", headers=auth_headers)
    assert msgs.status_code == 200
    assert any(m["body"] == "Hello United Amir" for m in msgs.json())


@pytest.mark.asyncio
async def test_parliament_and_news(client: AsyncClient):
    parl = await client.get("/api/politics/parliament")
    assert parl.status_code == 200
    data = parl.json()
    assert len(data["seats"]) == 20
    assert data["majority_needed"] == 11

    news = await client.get("/api/news")
    assert news.status_code == 200
    assert isinstance(news.json(), list)

    cabinet = await client.get("/api/cabinet")
    assert cabinet.status_code == 200
    assert len(cabinet.json()["seats"]) == 10
