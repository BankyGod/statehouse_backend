"""Smoke test travel + bank against a running server."""

import httpx

base = "http://127.0.0.1:8000"
c = httpx.Client(base_url=base, timeout=30.0)

# Fresh user each run
user = "traveler1"
reg = c.post(
    "/api/auth/register",
    json={"email": f"{user}@test.com", "username": user, "password": "password123"},
)
print("register", reg.status_code)
if reg.status_code == 400:
    pass  # already exists
login = c.post("/api/auth/login", data={"username": user, "password": "password123"})
token = login.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

me = c.get("/api/characters/me", headers=h)
if me.status_code == 404:
    states = c.get("/api/states").json()
    nf = next(s for s in states if s["slug"] == "new-frontier")
    ch = c.post(
        "/api/characters",
        headers=h,
        json={"display_name": "TravelerOne", "home_state_id": nf["id"]},
    )
    print("character", ch.status_code, ch.json()["cash"])
else:
    print("character exists", me.json()["cash"], "energy", me.json()["energy"])

char = c.get("/api/characters/me", headers=h).json()
print(
    "hud",
    {
        "cash": char["cash"],
        "energy": char["energy"],
        "traveling": char["is_traveling"],
        "heat": char["heat"],
    },
)

states = c.get("/api/states").json()
ash = next(s for s in states if s["slug"] == "ashfield")
quote = c.post("/api/travel/quote", headers=h, json={"to_state_id": ash["id"]})
print("quote", quote.status_code, quote.json())

dep = c.post("/api/bank/deposit", headers=h, json={"amount": 100})
print("deposit", dep.status_code, dep.json())

loan = c.post("/api/bank/loans", headers=h, json={"amount": 500})
print("loan", loan.status_code, loan.json() if loan.status_code < 500 else loan.text)

bank = c.get("/api/bank/me", headers=h)
print("bank", bank.status_code, bank.json())

if not char["is_traveling"]:
    trip = c.post("/api/travel/start", headers=h, json={"to_state_id": ash["id"]})
    print("travel", trip.status_code, trip.json())
    blocked = c.post("/api/jobs/work", headers=h)
    print("work_while_traveling", blocked.status_code, blocked.json())
