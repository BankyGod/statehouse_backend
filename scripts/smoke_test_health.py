import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
user = "medic1"
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
            json={"display_name": "MedicOne", "home_state_id": nf["id"]},
        ).status_code,
    )

health = c.get("/api/medical/me", headers=h)
print("health", health.status_code, health.json())

full = c.post("/api/medical/clinic", headers=h, json={"hp_amount": 10})
print("clinic_full", full.status_code, full.json())

# Try to take injury via rough crime
for i in range(8):
    r = c.post("/api/crime/commit", headers=h, json={"crime_type": "burglary"})
    data = r.json()
    print("crime", i, r.status_code, data.get("injury"), data.get("health"), data.get("is_jailed"))
    if data.get("is_jailed") or data.get("is_hospitalized"):
        break
    if data.get("health", 100) < 100:
        heal = c.post("/api/medical/clinic", headers=h, json={"hp_amount": 20})
        print("clinic_heal", heal.status_code, heal.json())
        break

char = c.get("/api/characters/me", headers=h).json()
print(
    "hud",
    char.get("health"),
    char.get("is_hospitalized"),
    char.get("is_jailed"),
    char.get("condition"),
)
