import httpx

base = "http://127.0.0.1:8000"
c = httpx.Client(base_url=base, timeout=30.0)
print("health", c.get("/health").json())
states = c.get("/api/states").json()
print("states", len(states), states[0]["name"])
r = c.post(
    "/api/auth/register",
    json={"email": "banky@test.com", "username": "banky", "password": "password123"},
)
print("register", r.status_code, r.text[:200])
login = c.post(
    "/api/auth/login", data={"username": "banky", "password": "password123"}
)
print("login", login.status_code, list(login.json().keys()))
token = login.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
nf = next(s for s in states if s["slug"] == "new-frontier")
ch = c.post(
    "/api/characters",
    headers=h,
    json={"display_name": "Banky", "home_state_id": nf["id"], "bio": "Life sim start"},
)
print("character", ch.status_code, ch.json())
jobs = c.get("/api/jobs/listings", headers=h).json()
print("jobs", len(jobs), jobs[0]["title"] if jobs else None)
hire = c.post("/api/jobs/hire", headers=h, json={"listing_id": jobs[0]["id"]})
print("hire", hire.status_code, hire.json())
work = c.post("/api/jobs/work", headers=h)
print("work", work.status_code, work.json())
crime = c.post("/api/crime/commit", headers=h, json={"crime_type": "street_theft"})
print("crime", crime.status_code, crime.json())
print("me", c.get("/api/characters/me", headers=h).json())
