import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
user = "chatter1"
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
    ch = c.post(
        "/api/characters",
        headers=h,
        json={"display_name": "ChatterOne", "home_state_id": nf["id"]},
    ).json()
    state_id = ch["home_state_id"]
    print("create", ch["id"], state_id)
else:
    state_id = me.json()["home_state_id"]
    print("existing", state_id)

blocked = c.post(
    f"/api/chat/states/{state_id}/messages",
    headers=h,
    json={"body": "visit https://evil.example"},
)
print("blocked", blocked.status_code, blocked.json())

post = c.post(
    f"/api/chat/states/{state_id}/messages",
    headers=h,
    json={"body": "Anyone hiring on the frontier?"},
)
print("post", post.status_code, post.json())

again = c.post(
    f"/api/chat/states/{state_id}/messages",
    headers=h,
    json={"body": "spam?"},
)
print("cooldown", again.status_code, again.json())

# Wrong state
other = c.get("/api/states").json()
ash = next(s for s in other if s["slug"] == "ashfield")
deny = c.post(
    f"/api/chat/states/{ash['id']}/messages",
    headers=h,
    json={"body": "hello ashfield"},
)
print("deny_other_state", deny.status_code, deny.json())

home = c.get("/api/chat/home/messages", headers=h).json()
print("home_msgs", len(home), home[-1]["body"] if home else None)
