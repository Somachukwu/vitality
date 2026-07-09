# Vita Backend

FastAPI backend for Vitality — handles auth, device ingestion (ESP32 wearable +
station), meal logging with food recognition, vitals, and the recommendation
engine. See the [root README](../README.md) for how this fits into the wider
project.

## Tech stack
FastAPI · SQLAlchemy · MySQL 8.4 · JWT auth (python-jose + passlib) · Pydantic Settings

## Project structure
```
app/
  main.py           — FastAPI app, CORS, router mounts, table creation on startup
  config.py         — Settings loaded from .env (pydantic-settings)
  database.py       — SQLAlchemy engine/session
  core/             — security (JWT, password hashing) and shared dependencies
  models/           — SQLAlchemy models (User, Device, Meal, Vitals, Recommendation)
  schemas/          — Pydantic request/response schemas
  routers/          — one router per resource (auth, users, devices, vitals, meals, food_recognition, recommendations)
food_cv/            — food recognition model (see food_cv/README.md)
recommendation_engine/  — rule + ML recommendation engine (see recommendation_engine/README.md)
sql/init.sql        — one-shot DB schema creation script
tests/test_api.py   — end-to-end smoke test against a running server
db_setup.py         — verify / reset / seed the database
diagnose.py         — checks device API key registration, server reachability, and a simulated ESP32 POST
uploads/meals/       — uploaded meal images (served at /uploads, gitignored)
```

## Setup

1. **Install dependencies**
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   ```
   Food recognition needs a separate, larger install — see `food_cv/README.md`:
   ```
   pip install tensorflow==2.17.0 numpy pillow
   ```

2. **Configure environment** — copy `.env.example` to `.env` and fill in real values:
   ```
   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
   JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES
   APP_ENV, CORS_ORIGINS
   ```

3. **Create the database** — run `sql/init.sql` once against your MySQL server
   (creates the database and all tables). `app/main.py` also runs
   `Base.metadata.create_all()` on every startup, so it will create any tables
   that don't exist yet and patch a couple of legacy columns automatically —
   `sql/init.sql` is the canonical schema reference.

4. **Run the server**
   ```
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   `--host 0.0.0.0` is required if you want ESP32 devices on the same network
   to reach it. Visit `http://localhost:8000/api/health` to confirm it's up.

## Utility scripts
- `python db_setup.py verify` — list all tables and row counts
- `python db_setup.py seed` — insert a demo user (`demo@vita.app` / `demo1234`)
- `python db_setup.py reset` — drop and recreate all tables (destroys data)
- `python diagnose.py` — checks DB device registration, server reachability, and simulates an ESP32 POST end-to-end; useful when a device won't connect

## Testing
- `python tests/test_api.py` — smoke-tests every endpoint against a running server (`http://127.0.0.1:8000` by default)
- `python -m recommendation_engine.test_smoke` — runs the recommendation engine against a synthetic day of data and prints the recommendations it fires
