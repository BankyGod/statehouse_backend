import sqlite3

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)


def auth(username: str, display: str, state_slug: str) -> tuple[dict, int]:
    c.post(
        "/api/auth/register",
        json={
            "email": f"{username}@test.com",
            "username": username,
            "password": "password123",
        },
    )
    token = c.post(
        "/api/auth/login", data={"username": username, "password": "password123"}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    me = c.get("/api/characters/me", headers=h)
    if me.status_code == 404:
        states = c.get("/api/states").json()
        st = next(s for s in states if s["slug"] == state_slug)
        ch = c.post(
            "/api/characters",
            headers=h,
            json={"display_name": display, "home_state_id": st["id"]},
        ).json()
        cid = ch["id"]
    else:
        cid = me.json()["id"]
    return h, cid


prez_h, prez_id = auth("prez1", "PrezOne", "amira-central")
mp_h, mp_id = auth("minmp1", "MinMpOne", "silkmarket")

conn = sqlite3.connect("statehouse.db")
conn.execute(
    "UPDATE nation_office SET president_character_id = ? WHERE id = 1", (prez_id,)
)
conn.execute(
    "UPDATE states SET mp_character_id = ? WHERE slug = 'silkmarket'", (mp_id,)
)
conn.commit()
conn.close()

cabinet = c.get("/api/cabinet").json()
print("cabinet seats", len(cabinet["seats"]), cabinet["seats"][0]["name"])

appoint = c.post(
    "/api/cabinet/appoint",
    headers=prez_h,
    json={"portfolio": "trade", "character_id": mp_id},
)
print("appoint", appoint.status_code, appoint.json())

mine = c.get("/api/cabinet/me", headers=mp_h).json()
print("mp seat", mine)

# President cannot appoint non-MP
fail = c.post(
    "/api/cabinet/appoint",
    headers=prez_h,
    json={"portfolio": "health", "character_id": prez_id},
)
print("self_appoint", fail.status_code, fail.json())

resign = c.post("/api/cabinet/resign", headers=mp_h)
print("resign", resign.status_code, resign.json())

news = c.get("/api/news?category=politics").json()
print("headlines", [n["headline"] for n in news[:4]])
