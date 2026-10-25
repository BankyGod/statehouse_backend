# The State House — Backend

Python FastAPI backend for **United Amir**: a Torn-like text life sim (careers, education, business, housing, health, travel, bank, crime, optional politics, cabinet, news, state chat).

Frontend integration notes: [`docs/FRONTEND_GUIDE.md`](docs/FRONTEND_GUIDE.md)

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2 (async)
- SQLite for local dev; **Postgres** via `postgresql+asyncpg://...`
- Alembic migrations
- JWT auth (OAuth2 password flow)
- Seeded world data on startup (20 states, jobs, housing, politics, cabinet, news)

## Quick start (SQLite)

```powershell
cd c:\Users\USER\Documents\github\statehouse_backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Docs: http://127.0.0.1:8000/docs

Use **Python 3.11** (recommended).

## Postgres

1. Create a database and user.
2. Set in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/statehouse
```

3. Run migrations (preferred in shared/staging/prod):

```powershell
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Local SQLite still auto-creates tables on startup for fast iteration. Prefer Alembic once the schema is shared.

## Migrations

```powershell
# After model changes:
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

## Tests

```powershell
pytest -q
```

## Core player flow

1. `POST /api/auth/register` → `POST /api/auth/login`
2. `GET /api/states` → pick home state
3. `POST /api/characters`
4. Jobs / education / business / housing / travel / bank / medical / crime
5. Optional: politics, legislation, cabinet, chat, news

## Time model

- Calendar ratio **8:1** (`GAME_TIME_RATIO`)
- Long activities use short real timers but age the character by full game years
