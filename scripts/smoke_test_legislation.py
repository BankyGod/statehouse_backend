import sqlite3

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
user = "lawmaker1"
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
    ash = next(s for s in states if s["slug"] == "ashfield")
    ch = c.post(
        "/api/characters",
        headers=h,
        json={"display_name": "LawMakerOne", "home_state_id": ash["id"]},
    ).json()
    print("create", ch["id"])
    # Make them MP for Ashfield for this smoke test
    conn = sqlite3.connect("statehouse.db")
    conn.execute(
        "UPDATE states SET mp_character_id = ? WHERE slug = 'ashfield'",
        (ch["id"],),
    )
    conn.commit()
    conn.close()
else:
    print("existing", me.json()["id"])

news = c.get("/api/news").json()
print("news", len(news), news[0]["headline"] if news else None)

budget = c.get("/api/legislation/budget/current").json()
print("budget", budget)

bill = c.post(
    "/api/legislation/bills",
    headers=h,
    json={
        "title": "Farm Support Act",
        "summary": "Subsidies for Ashfield grain cooperatives and rural clinics.",
    },
)
print("propose", bill.status_code, bill.json())
bill_id = bill.json()["id"]

vote = c.post(
    f"/api/legislation/bills/{bill_id}/vote",
    headers=h,
    json={"choice": "yes"},
)
print("vote", vote.status_code, vote.json())

bills = c.get("/api/legislation/bills").json()
print("bills", len(bills), bills[0]["status"], "npc_yes", bills[0]["npc_yes"])

if budget.get("budget"):
    bv = c.post(
        f"/api/legislation/budget/{budget['budget']['id']}/vote",
        headers=h,
        json={"choice": "yes"},
    )
    print("budget_vote", bv.status_code, bv.json())

news2 = c.get("/api/news?category=politics").json()
print("politics_news", [n["headline"] for n in news2[:3]])
