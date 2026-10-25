import sqlite3
from datetime import datetime, timedelta, timezone

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
user = "broker1"
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
        json={"display_name": "BrokerOne", "home_state_id": nf["id"]},
    ).json()
    cid = ch["id"]
    home_state_id = ch["home_state_id"]
    print("create", cid)
else:
    cid = me.json()["id"]
    home_state_id = me.json()["home_state_id"]

# Bank extras
c.post("/api/bank/deposit", headers=h, json={"amount": 200})
bank = c.get("/api/bank/me", headers=h).json()
print("bank", bank["bank_balance"], "apr", bank["savings_apr"])

market = c.get("/api/stocks/market").json()["listings"]
print("gov listings", len(market), [L["symbol"] for L in market[:4]])
gov = next(L for L in market if L["symbol"] == "UATSY")

# Fund cash for stock buy via loan -> withdraw
c.post("/api/bank/loans", headers=h, json={"amount": 2000})
c.post("/api/bank/withdraw", headers=h, json={"amount": 1500})
buy = c.post(
    "/api/stocks/buy",
    headers=h,
    json={"listing_id": gov["id"], "shares": 10},
)
print("buy_gov", buy.status_code, buy.json())

sell = c.post(
    "/api/stocks/sell",
    headers=h,
    json={"listing_id": gov["id"], "shares": 4},
)
print("sell", sell.status_code, sell.json())

# Prepare a business for IPO via DB (active + cash + old enough)
biz = c.post(
    "/api/businesses",
    headers=h,
    json={
        "name": "Frontier Freight",
        "sector": "logistics",
        "state_id": home_state_id,
        "local_address": "1 Homestead Yard",
        "description": "Haulage across Oasis Reach",
    },
)
print("biz", biz.status_code, biz.json() if biz.status_code < 500 else biz.text)
if biz.status_code == 201:
    bid = biz.json()["id"]
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    conn = sqlite3.connect("statehouse.db")
    conn.execute(
        "UPDATE businesses SET status='ACTIVE', cash_balance=5000, "
        "registered_at=?, is_public=0 WHERE id=?",
        (old, bid),
    )
    conn.execute(
        "UPDATE characters SET reputation = 20, cash = cash + 1000 WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()

    ipo = c.post(
        "/api/stocks/ipo",
        headers=h,
        json={
            "business_id": bid,
            "symbol": "FFRGT",
            "total_shares": 5000,
            "ipo_price": 12.0,
            "founder_keep_pct": 0.4,
        },
    )
    print("ipo", ipo.status_code, ipo.json() if ipo.status_code < 500 else ipo.text)

port = c.get("/api/stocks/portfolio", headers=h).json()
print("portfolio", port)

txs = c.get("/api/bank/transactions", headers=h).json()
print("bank_txs", [(t["tx_type"], t["amount"]) for t in txs[:5]])
