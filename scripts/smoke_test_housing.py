import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
user = "houser1"
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
    created = c.post(
        "/api/characters",
        headers=h,
        json={"display_name": "HouserOne", "home_state_id": nf["id"]},
    )
    print("create", created.status_code, created.json())
else:
    print("existing", me.json())

char = c.get("/api/characters/me", headers=h).json()
print(
    "hud housing",
    char["is_homeless"],
    char["active_residence_id"],
    char["max_energy"],
)

home = c.get("/api/housing/me", headers=h)
print("residence", home.status_code, home.json())

listings = c.get("/api/housing/listings", headers=h).json()
print("listings", len(listings), [L["title"] for L in listings])

room = next(L for L in listings if L["title"] == "Single room")
# May need cash from loan
c.post("/api/bank/loans", headers=h, json={"amount": 500})
rented = c.post("/api/housing/rent", headers=h, json={"listing_id": room["id"]})
print("rent", rented.status_code, rented.json() if rented.status_code < 500 else rented.text)

char2 = c.get("/api/characters/me", headers=h).json()
print("after rent", char2["is_homeless"], char2["max_energy"], char2["cash"])
