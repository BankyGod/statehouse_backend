# The State House: United Amir — Frontend Guide (React + Vite)

This document explains **what the game is**, **how players experience it**, and **what the React frontend should build** against the current Python backend.

- Backend API docs (live): `http://127.0.0.1:8000/docs`
- Backend base URL (dev): `http://127.0.0.1:8000`
- Stack for FE: **React + Vite** (TypeScript recommended)
- Allowed CORS origins today: `http://localhost:3000`, `http://localhost:5173`

---

## 1. What this product is

**The State House** is a persistent multiplayer **text life simulation** set in a fictional country called **United Amir**.

It is closest in feel to **Torn** (torn.com):

- You create a character and live a compressed life
- You spend **energy**, earn **cash**, wait on **timers**, and climb status
- The world keeps running whether you are online or not
- Numbers and actions matter more than cinematic graphics

It is **not** a politics-only game. Politics exists later as an optional path. Players can do almost anything people do in real life: study, work, run a business, travel between states, commit crime (risky), join security, etc.

**Core fantasy:**  
“I live in United Amir. I pick a home state, build a life, and become whoever I want — worker, tycoon, criminal, professional, or eventually a politician.”

---

## 2. The country: United Amir

United Amir has **20 states**. Every player chooses one **home state** at character creation.

That home state is their:

- Identity and local community
- Place they can live and work **without permits**
- Constituency for voting / running for MP later (optional politics)
- Default “home city” screen in the UI

Players can work or open businesses in other states, but that needs **permits** and fees. This creates friction, local economies, and state rivalry.

### The 20 states (use these exact names)

| State | Capital | Flavour |
|---|---|---|
| Amira Central | Amirabad | Capital: government, media, high rents |
| Port Meridian | Meridian City | Port, shipping, navy, logistics |
| Golden Coast | Lagune | Tourism, hospitality, fishing |
| Ashfield | Ashfield Town | Farming / food |
| Riverbend | Bendora | Rivers, rice, inland markets |
| Ironridge | Forgehaven | Mining, steel, factories |
| Coppervale | Valeport | Mining/refining, lower rents, hazardous work |
| Greenwood | Timberly | Forestry, eco-tourism |
| Sunplain | Solara | Cash crops, solar/agribusiness |
| Northwatch | Bastion | Military / border security (high crime catch rate) |
| Lakeshire | Clearwater | Fishing, resorts, light industry |
| Highlands | Cairn Peak | Plateau farms, herding, quarrying |
| Oasis Reach | Mirage Wells | Arid trucking hub, sparse, lower security |
| Scholar's Haven | College Row | Universities, research, students |
| Silkmarket | Bazaar City | Trade, crafts, textiles |
| Blackreef | Deep Harbour | Oil/gas, high wages, boom-bust |
| Harmony Bay | Sanctum | Culture/NGOs/services |
| Railford | Junction | Rail/freight crossroads |
| Crystal Springs | Spa City | Health tourism, pharma light |
| New Frontier | Homestead | Cheap land, startups, weak services (big starter bonus) |

Frontend should make state choice feel meaningful: show population, average income, starting bonus, tax vibe, and security level (`crime_catch_rate`).

---

## 3. Time model (important for UX)

Calendar ratio is **8:1**:

- 4 game years ≈ 6 real months
- Character **ages by full game time** even when the real wait is short

Example:

- A bachelor’s degree ages you **+4 years**
- But the real-world wait is about **14 days**
- UI must show both: “Completes in 13d 4h” and “You will age +4.0 years”

Same idea for diplomas, law school, medical school, military basic, business registration, etc.

Loans and elections (when added) stay longer on the real clock so the world does not feel disposable.

---

## 4. What a player can do (product pillars)

### Always-on character stats (HUD)

Show these everywhere after login:

| Stat | Meaning |
|---|---|
| Cash | Spendable money |
| Bank | Savings (backend field exists; banking UI later) |
| Energy | Spent on work/crime; gates actions |
| Age | Increases when long activities complete |
| Heat | Criminal attention; high heat blocks permits/jobs |
| Reputation | Social/political standing (mostly future systems) |
| Jailed | Hard lockout until `jail_until` |

Torn-style: top bar with cash / energy / age / heat, plus notifications.

### Life systems (built or partially built now)

1. **Identity** — account + one character + home state  
2. **Jobs** — browse listings, hire, work shifts for wages  
3. **Education** — enroll in tracks; wait; gain education level + age  
4. **Business** — register a company in a state (pending → active)  
5. **Permits** — work / business / travel for other states  
6. **Crime** — optional, profitable short-term, punished hard  
7. **States** — browse and identify with local flavour  

### Built in this backend pass

7. **Travel** — quote + start trip; arrive on timer; blocks actions while traveling  
8. **Bank** — deposit / withdraw / loans / transfers / savings interest / transaction ledger  
9. **Stocks (separate)** — gov + business IPOs; buy/sell shares; investors exit only by selling  
10. **Energy regen** — 1 energy every 5 minutes (on `/characters/me` tick)  
11. **Heat decay** — slowly drops while free  
12. **Housing** — free home-state hostel on create; rent/buy; weekly rent auto-pay; eviction  
13. **Health** — HP, clinic heal, hospital stay (locks actions), crime injuries, slow regen  
14. **Politics (optional)** — 20-seat parliament, elections, MP + presidential candidacy & voting  
15. **Legislation** — MPs propose/vote bills; budget readings; presidential veto  
16. **Newspaper** — national/state headlines from elections, bills, budgets  
17. **Cabinet** — 10 ministries; president appoints MPs; weekly minister salary  
18. **State chat** — per-state channels; home or current state; rate-limited  

### Also built (life loop depth)

19. **Business ops** — revenue every ~6h from staff, weekly payroll, deposit/withdraw (no withdraw if public)  
20. **Employees** — hire NPCs or players; player wages paid on payroll  
21. **Activity + notifications feed** — `/api/activities/me`, `/api/activities/notifications`  
22. **Gym** — train strength/defense/speed/dexterity for energy  
23. **Nerve + deeper crime** — tiers, nerve cost/regen, history, loot drops  
24. **Inventory + player market** — shop, use items, list/buy peer listings  
25. **Jail bail** — `/api/jail/me`, `/api/jail/bail` (+ hospital `seconds_remaining`)  
26. **Social** — friends/enemies, attacks, DMs, factions, world events  
27. **Peer stock orders** — place/fill sell orders between players  

**Realtime:** Socket.IO at `/socket.io` (see §18). Prefer sockets over polling for feed, HUD, and chat.

Backend hardening: `pytest -q` (5 smoke tests), Alembic (`alembic upgrade head`), Postgres via `postgresql+asyncpg://...` (install `asyncpg` when needed).

---

## 5. Crime and security (tone)

Crime is **allowed for all players**, but security is intentionally tight:

- High catch chance (especially Northwatch / Amira Central)
- Heat accumulates
- Jail locks actions
- Criminal record blocks some jobs and business permits
- Low-security states are easier but often poorer / riskier in other ways

Frontend should never present crime as the “main path.” It is a dangerous side path with scary confirm modals.

---

## 6. Player journey (first session)

This is the flow FE must support end-to-end:

1. **Register** account  
2. **Login** → receive JWT  
3. If no character → **Create character**  
   - Enter display name  
   - Browse 20 states  
   - Confirm home state (warn: mostly permanent; 3-day one-time reset)  
4. Land on **Dashboard / City**  
5. Take a starter job → work a shift → see cash/energy change  
6. Optionally peek education / business / crime  

That first loop is the acceptance test for “frontend talks to backend.”

---

## 7. Information architecture (React routes)

Suggested Vite React Router map:

```text
/login
/register
/create-character

/                       → Dashboard (HUD + quick actions)
/states                 → State directory
/states/:slug           → State profile
/jobs                   → Job market + current job + Work button
/education              → Catalog + enrollments + timers
/business               → Register + my businesses
/permits                → Apply + my permits
/crime                  → Catalog + commit (confirm modal)
/profile                → Character sheet / record / home-state reset
```

Optional disabled stubs:

```text
/travel
/bank
/housing
/politics
```

---

## 8. UI tone (Torn-like, modern React)

Design goals:

- Dense, gamey, information-first — not a marketing landing page
- Action pages: list → select → confirm → result toast
- Timers visible
- State identity colours/icons help, but keep readability high
- Mobile usable, desktop primary

Avoid turning the first screen into a politics campaign dashboard. Politics is optional later.

Recommended layout:

```text
┌──────────────────────────────────────────────┐
│ Logo | Cash | Energy | Age | Heat | Profile  │  ← HUD
├────────────┬─────────────────────────────────┤
│ Nav        │  Page content                   │
│ Dashboard  │  Lists, forms, timers, CTAs     │
│ Jobs       │                                 │
│ Education  │                                 │
│ Business   │                                 │
│ Crime      │                                 │
│ States     │                                 │
└────────────┴─────────────────────────────────┘
```

---

## 9. Auth & API client rules (React)

### Auth

- `POST /api/auth/register` — JSON body  
- `POST /api/auth/login` — **x-www-form-urlencoded** (`username`, `password`) because OAuth2 password flow  
- Response: `{ access_token, token_type: "bearer" }`  
- Store token (`localStorage` or memory + persist)  
- Send header: `Authorization: Bearer <token>`  
- `GET /api/auth/me` for session restore  

### API helper pattern

```ts
// pseudo
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

Env example:

```env
VITE_API_URL=http://127.0.0.1:8000
```

### Error handling

Backend errors usually look like:

```json
{ "detail": "Not enough energy" }
```

or validation arrays. Show `detail` in toasts/banners.

Common cases to handle in UI:

- 401 → redirect login  
- 404 on `/api/characters/me` → redirect create-character  
- 403 jailed / permit required / security flag  
- 400 insufficient funds / energy / state full  

### Refresh rule

After every mutating action (`work`, `commit`, `enroll`, `hire`, `apply`, register business), refetch:

- `GET /api/characters/me`

Timers: listen for Socket.IO `activity` / `character` events; optional light poll only as fallback.

---

## 10. Backend endpoint map (current MVP)

Public / auth:

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | status |
| POST | `/api/auth/register` | JSON |
| POST | `/api/auth/login` | form body |
| GET | `/api/auth/me` | JWT |

States:

| Method | Path |
|---|---|
| GET | `/api/states` |
| GET | `/api/states/{id}` |
| GET | `/api/states/slug/{slug}` |

Character:

| Method | Path |
|---|---|
| POST | `/api/characters` |
| GET | `/api/characters/me` |
| POST | `/api/characters/me/home-state/reset` |

Jobs:

| Method | Path |
|---|---|
| GET | `/api/jobs/listings?state_id=` |
| POST | `/api/jobs/hire` |
| GET | `/api/jobs/me` |
| POST | `/api/jobs/work` |

Education:

| Method | Path |
|---|---|
| GET | `/api/education/catalog` |
| POST | `/api/education/enroll` |
| GET | `/api/education/me` |

Permits:

| Method | Path |
|---|---|
| POST | `/api/permits/apply` |
| GET | `/api/permits/me` |

Business:

| Method | Path |
|---|---|
| POST | `/api/businesses` |
| GET | `/api/businesses/me` | includes `employee_count`, lifetime revenue/wages |
| GET | `/api/businesses/{id}/employees` | staff roster |
| POST | `/api/businesses/{id}/employees/hire` | `{ role?, display_name? }` NPC hire |
| POST | `/api/businesses/{id}/employees/hire-player` | `{ display_name, role?, wage_per_week? }` |
| DELETE | `/api/businesses/{id}/employees/{employee_id}` | fire |
| POST | `/api/businesses/{id}/deposit` | `{ amount }` owner cash → company |
| POST | `/api/businesses/{id}/withdraw` | `{ amount }` (blocked if public) |

Employee roles: `labourer | clerk | specialist | manager | executive`

| GET | `/api/activities/me` | timers / completed actions |
| GET | `/api/activities/notifications` | feed |
| POST | `/api/activities/notifications/read` | mark read |
| GET | `/api/gym/catalog` |
| POST | `/api/gym/train` | `{ stat }` |
| GET | `/api/crime/history` |
| GET | `/api/inventory/shop` / `/me` |
| POST | `/api/inventory/shop/buy` | `{ item_key, quantity? }` |
| POST | `/api/inventory/use/{item_key}` |
| GET | `/api/inventory/market` |
| POST | `/api/inventory/market/sell` / `/buy` |
| GET | `/api/jail/me` | bail cost + countdown |
| POST | `/api/jail/bail` |
| GET/POST | `/api/social/...` | friends, enemies, attack, DMs, factions, events |
| GET/POST | `/api/stocks/orders` | peer sell book + fill |

Crime:

| Method | Path |
|---|---|
| GET | `/api/crime/catalog` |
| POST | `/api/crime/commit` |

Travel:

| Method | Path |
|---|---|
| POST | `/api/travel/quote` | `{ to_state_id }` |
| POST | `/api/travel/start` | `{ to_state_id }` |

Bank (not stocks — keep UI separate):

| Method | Path |
|---|---|
| GET | `/api/bank/me` | cash, bank, APR, fee, loans |
| GET | `/api/bank/transactions` | ledger |
| POST | `/api/bank/deposit` | `{ amount }` |
| POST | `/api/bank/withdraw` | `{ amount }` |
| POST | `/api/bank/transfer` | `{ to_display_name, amount }` (+ fee) |
| POST | `/api/bank/loans` | `{ amount }` → funds **bank** |
| POST | `/api/bank/loans/{id}/repay` | `{ amount }` from bank then cash |

Savings interest accrues daily on `bank_balance` (default 4% APR).

Stocks (separate exchange):

| Method | Path |
|---|---|
| GET | `/api/stocks/market` | gov + public businesses |
| GET | `/api/stocks/portfolio` | your holdings + P/L |
| POST | `/api/stocks/ipo` | list your business (requirements) |
| POST | `/api/stocks/buy` | `{ listing_id, shares }` from float |
| POST | `/api/stocks/sell` | `{ listing_id, shares }` → **your** cash |

**Share rules for FE copy:**
- IPO / primary buy: money funds the **company or government**, not the owner’s pocket as “investor cash”
- After that, investors only exit by **selling shares**
- The business **cannot seize or withdraw** shareholder positions
- Company may use its own `cash_balance` for operations; that is not the same as redeeming shares
- IPO needs: active business, enough company cash, age, owner reputation, listing fee, symbol

Character HUD also includes: `is_traveling`, `travel_until`, `travel_destination_id`, `is_homeless`, `active_residence_id`, `health`, `max_health`, `is_hospitalized`, `hospital_until`, `condition`.

Housing:

| Method | Path |
|---|---|
| GET | `/api/housing/listings?state_id=` |
| GET | `/api/housing/me` |
| POST | `/api/housing/rent` | `{ listing_id }` |
| POST | `/api/housing/buy` | `{ listing_id }` |
| POST | `/api/housing/leave` |

Notes: must be **in** the listing’s state to rent/buy (travel first). Better homes raise `max_energy`. Weekly rent auto-deducts from cash then bank; 2 misses → eviction.

Medical:

| Method | Path |
|---|---|
| GET | `/api/medical/me` |
| POST | `/api/medical/clinic` | `{ hp_amount }` instant heal for cash |
| POST | `/api/medical/hospital` | admit; blocks actions until `hospital_until` |

Show HP on the HUD. Hospitalized / jailed / traveling all disable action buttons. Crystal Springs & Amira Central clinics/hospitals are cheaper/faster.

Politics (optional path):

| Method | Path |
|---|---|
| GET | `/api/politics/parliament` | 20 seats + president (NPC or player) |
| GET | `/api/politics/elections/current` | status + timers |
| GET | `/api/politics/elections/{id}/candidates?race_type=&state_id=` |
| POST | `/api/politics/elections/{id}/run` | `{ race_type: "mp"\|"president", slogan }` |
| POST | `/api/politics/elections/{id}/vote` | `{ candidacy_id }` |
| POST | `/api/politics/elections/{id}/resolve` | tally & seat winners |

Rules for FE copy:
- Vote for **MP only in your home state**; president is national  
- One ballot per race per election  
- MP min age **25**, president **30** (config)  
- Candidacy fees; high heat / criminal record can block runs  
- Empty seats keep **NPC MPs**; majority 11, veto override 14  
- First seeded election starts in **voting** so you can test immediately

Legislation & news:

| Method | Path |
|---|---|
| GET | `/api/legislation/bills?status=` |
| POST | `/api/legislation/bills` | `{ title, summary }` MP only |
| POST | `/api/legislation/bills/{id}/vote` | `{ choice: yes\|no\|abstain }` |
| POST | `/api/legislation/bills/{id}/veto` | president only |
| GET | `/api/legislation/budget/current` |
| POST | `/api/legislation/budget/{id}/vote` | `{ choice: yes\|no }` |
| GET | `/api/news?limit=&category=&state_id=` |

Bill debate ~2.5 real days; NPC MPs auto-lean so tallies can reach majority 11. Budget cycles ~every 45 days.

Cabinet:

| Method | Path |
|---|---|
| GET | `/api/cabinet` | 10 seats (NPC caretakers until appointed) |
| GET | `/api/cabinet/me` | your ministry if any |
| POST | `/api/cabinet/appoint` | `{ portfolio, character_id }` president only |
| POST | `/api/cabinet/dismiss` | `{ portfolio }` president only |
| POST | `/api/cabinet/resign` | leave your post |

Portfolios: `finance`, `defence`, `health`, `education`, `interior`, `trade`, `justice`, `agriculture`, `energy`, `transport`.  
By default ministers must be **sitting MPs**. Weekly salary `$400` (config).

Chat:

| Method | Path |
|---|---|
| GET | `/api/chat/home/messages` | your home-state channel |
| GET | `/api/chat/states/{state_id}/messages?limit=&before_id=` | history |
| POST | `/api/chat/states/{state_id}/messages` | `{ body }` |

Rules: post only in **home state** or **current state**; max 280 chars; **10s** cooldown; links blocked. Prefer Socket.IO `chat:message` (auto-joined to home/current state rooms).

Enums FE should type:

- Education tracks: `short_course | diploma | bachelors | law | masters | medical | military_basic`
- Permit types: `work | business | travel`
- Crime types: `street_theft | burglary | fraud | smuggling | fencing`

---

## 11. Key data shapes (frontend models)

### Character (HUD source of truth)

```ts
type Character = {
  id: number;
  display_name: string;
  home_state_id: number;
  current_state_id: number;
  home_state_locked: boolean;
  home_state_chosen_at: string; // ISO datetime
  age_years: number;
  cash: number;
  bank_balance: number;
  energy: number;
  max_energy: number;
  reputation: number;
  heat: number;
  is_jailed: boolean;
  jail_until: string | null;
  bio: string | null;
  criminal_record_summary: string | null;
};
```

### State summary (picker)

```ts
type StateSummary = {
  id: number;
  slug: string;
  name: string;
  capital: string;
  economic_profile: string;
  population_count: number;
  population_cap: number;
  is_open: boolean;
  average_income: number;
  starting_bonus: number;
  crime_catch_rate: number;
};
```

Currency is **$** (dollars). Display as `$1,234.56`.

---

## 12. Screen-by-screen behaviour

### Create character

- Load `/api/states`
- Disable full/closed states (`is_open === false`)
- Show starting bonus prominently (New Frontier is attractive on purpose)
- Show security hint from `crime_catch_rate`
- Confirm modal: “Home state is permanent after 3 days (one reset only).”

### Dashboard

- Greeting + home state name
- Quick actions: Work, Find job, Study, Business, Crime
- If jailed: full-width warning, disable action buttons

### Jobs

- Listings for current state (or selected state)
- Hire replaces current job
- Work spends energy, pays wage immediately (current backend behaviour)
- If listing is outside home state, player needs active work permit first

### Education

- Catalog cards with cost, real days, age gain, level
- One active enrollment at a time
- Progress list with countdown to `completes_at`
- On complete, age increases (visible on HUD)

### Permits

- Choose target state + type
- Show fee outcome from response
- List active/expired permits with expiry dates
- High heat may be denied — show backend message

### Business

- Form: name, sector, state, local address
- Non-home state requires business permit
- Status badge: Pending / Active
- Pending until registration timer ends

### Crime

- Catalog with energy, payout range, heat, jail hours, fine
- Strong confirm: “High chance of arrest in this state”
- Result panel from API (`message`, caught, payout, jail)

---

## 13. Suggested React project structure

```text
src/
  api/           # axios/fetch clients per domain
  components/    # Hud, StateCard, Timer, ConfirmModal...
  features/
    auth/
    character/
    states/
    jobs/
    education/
    business/
    permits/
    crime/
  hooks/         # useCharacter, useAuth
  pages/
  types/
  App.tsx
  main.tsx
```

State management: start with React Query (TanStack Query) + context for auth. It fits timer refetching well.

---

## 14. Acceptance checklist for FE ↔ BE testing

- [ ] Register + login works; token persists on refresh  
- [ ] 20 states render with flavour  
- [ ] Character creation works; HUD shows cash/energy/age  
- [ ] Hire + work updates cash/energy  
- [ ] Education enroll shows timer  
- [ ] Permit apply works and appears in list  
- [ ] Business register creates pending business  
- [ ] Crime commit updates heat and can jail  
- [ ] Jailed state blocks actions in UI  
- [ ] API errors surface as readable messages  

---

## 15. One-sentence pitch for designers/devs

**United Amir is a Torn-like life MMO in the browser: pick a state, spend energy, chase money and status through jobs, school, business, or crime — with politics as a late optional endgame, not the only goal.**

---

## 16. Who owns what

| Team | Owns |
|---|---|
| Frontend (React/Vite) | Screens, HUD, timers UX, forms, auth storage, empty/error states |
| Backend (FastAPI) | Rules, timers truth, economy, security rolls, persistence |
| Shared | Enum names, route contracts, error `detail` strings, OpenAPI |

When in doubt, trust **`/docs`** over this file if they ever diverge — then update this guide.

---

## 17. Demo mogul account (ready-made)

Seeded on server start (idempotent). Login:

| Field | Value |
|---|---|
| Username | `mogul` |
| Password | `password123` |
| Character | `TycoonBanky` |

Preloaded:

- **4 degrees + 1 master's** (Business Admin, CS, Economics, LLB, MBA) — all completed
- **Amir Consolidated Holdings** — active conglomerate in Amira Central
- **~40 NPC employees** across labourer → executive
- Starting cash ~$25k + bank ~$75k + company cash ~$150k

Re-seed manually: `python scripts/seed_demo_mogul.py`

---

## 18. Socket.IO realtime

Run uvicorn against the combined ASGI app:

```bash
uvicorn app.main:asgi_app --host 127.0.0.1 --port 8000 --reload
```

Path: `http://127.0.0.1:8000/socket.io`

### Client (React)

```bash
npm i socket.io-client
```

```ts
import { io } from "socket.io-client";

const socket = io(import.meta.env.VITE_API_URL, {
  path: "/socket.io",
  auth: { token: localStorage.getItem("token") },
  transports: ["websocket", "polling"],
});

socket.on("connected", (p) => console.log("rt ok", p));
socket.on("character", (hud) => { /* update cash/energy/nerve/jail */ });
socket.on("activity", (a) => { /* timers + feed */ });
socket.on("notification", (n) => { /* toast / bell */ });
socket.on("chat:message", (m) => { /* append to state chat */ });

socket.emit("ping_hud");
socket.emit("join_state", { state_id: 3 }, (ack) => {});
```

| Event | Direction | Payload |
|---|---|---|
| `connected` | server → client | `{ user_id, character_id, display_name }` |
| `character` | server → client | HUD snapshot |
| `activity` | server → client | timers / completions |
| `notification` | server → client | feed item |
| `chat:message` | server → client | state chat |
| `join_state` / `leave_state` | client → server | `{ state_id }` |
| `ping_hud` | client → server | tick + emit `character` |

Auth: JWT in `auth.token`. Server joins `character:{id}`, `user:{id}`, home/current `state:{id}` rooms. REST feeds remain for history / reconnect catch-up.
