import sqlite3

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
user = "polit1"
c.post(
    "/api/auth/register",
    json={"email": f"{user}@test.com", "username": user, "password": "password123"},
)
token = c.post(
    "/api/auth/login", data={"username": user, "password": "password123"}
).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

me = c.get("/api/characters/me", headers=h)
if me.status_code == 404:
    states = c.get("/api/states").json()
    nf = next(s for s in states if s["slug"] == "new-frontier")
    print(
        "create",
        c.post(
            "/api/characters",
            headers=h,
            json={"display_name": "PolitOne", "home_state_id": nf["id"]},
        ).json()["id"],
    )

parliament = c.get("/api/politics/parliament")
print("parliament seats", len(parliament.json()["seats"]), "president", parliament.json()["president"])

election = c.get("/api/politics/elections/current").json()["election"]
print("election", election["id"], election["status"])

# Age character to eligible MP (dev DB tweak for smoke)
conn = sqlite3.connect("statehouse.db")
conn.execute("UPDATE characters SET age_years = 26 WHERE display_name = 'PolitOne'")
conn.commit()
conn.close()

c.post("/api/bank/loans", headers=h, json={"amount": 500})
run = c.post(
    f"/api/politics/elections/{election['id']}/run",
    headers=h,
    json={"race_type": "mp", "slogan": "Jobs for New Frontier"},
)
print("run", run.status_code, run.json() if run.status_code < 500 else run.text)
cand_id = run.json()["id"]

vote = c.post(
    f"/api/politics/elections/{election['id']}/vote",
    headers=h,
    json={"candidacy_id": cand_id},
)
print("vote", vote.status_code, vote.json())

resolved = c.post(
    f"/api/politics/elections/{election['id']}/resolve",
    headers=h,
)
print("resolve", resolved.status_code)
prez = resolved.json().get("president")
mps = [r for r in resolved.json().get("mp_results", []) if not r.get("npc")]
print("player mp wins", mps[:3], "president", prez)

parliament2 = c.get("/api/politics/parliament").json()
nf_seat = next(s for s in parliament2["seats"] if s["state_slug"] == "new-frontier")
print("nf seat", nf_seat)
