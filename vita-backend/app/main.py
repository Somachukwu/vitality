import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.models import Device, GoogleHealthToken, Meal, MealItem, Recommendation, SleepSession, User, Vitals  # noqa: F401 — ensures all tables are registered
from app.routers import auth, devices, food_recognition, meals, recommendations, users, vitals, google_health


async def _warmup_model_task():
    """Background task: pre-warm food recognition AI model in RAM and compile graph without blocking server boot."""
    def _warmup():
        try:
            import numpy as np
            from food_cv import config
            from food_cv.inference import _load_model
            model, _ = _load_model()
            # Feed a single dummy batch to trigger TensorFlow kernel compilation
            dummy_batch = np.zeros((1, config.IMAGE_SIZE[0], config.IMAGE_SIZE[1], 3), dtype=np.float32)
            model.predict(dummy_batch, verbose=0)
            print("INFO: Food recognition AI model pre-warmed and computational graph compiled in RAM.")
        except Exception as exc:
            print("NOTICE: Food recognition model warmup skipped:", exc)

    await asyncio.to_thread(_warmup)


async def _keep_alive_task():
    """Background task: periodically pings the public health endpoint to prevent Render free-tier idle spin-down."""
    url = settings.KEEP_ALIVE_URL or settings.RENDER_EXTERNAL_URL
    if not url:
        return

    health_url = f"{url.rstrip('/')}/api/health"
    print(f"INFO: Keep-alive service active. Target: {health_url} (every 14m)")

    try:
        import httpx
    except ImportError:
        print("NOTICE: httpx not available for keep-alive task.")
        return

    while True:
        try:
            await asyncio.sleep(14 * 60)  # Wait 14 minutes
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(health_url)
                if res.status_code == 200:
                    print("INFO: Keep-alive ping successful.")
                else:
                    print(f"NOTICE: Keep-alive ping returned status {res.status_code}")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"NOTICE: Keep-alive ping error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm AI model asynchronously on startup so first request has zero cold-start delay
    asyncio.create_task(_warmup_model_task())
    keep_alive = asyncio.create_task(_keep_alive_task())
    yield
    keep_alive.cancel()


def _run_migrations():
    """Apply schema changes to existing tables that create_all() cannot handle."""
    inspector = inspect(engine)
    with engine.connect() as conn:
        # ── devices table ───────────────────────────────────────────────────────
        if "devices" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("devices")}
            if "device_type" not in cols:
                conn.execute(text(
                    "ALTER TABLE devices ADD COLUMN device_type "
                    "ENUM('wearable','station') NOT NULL DEFAULT 'wearable'"
                ))
                conn.commit()

        # ── users table ─────────────────────────────────────────────────────────
        if "users" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "health_conditions" not in cols:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN health_conditions JSON NULL"
                ))
                conn.commit()
            # Make password_hash nullable to support future Google-only accounts
            if "password_hash" in cols:
                conn.execute(text(
                    "ALTER TABLE users MODIFY COLUMN password_hash VARCHAR(255) NULL"
                ))
                conn.commit()

        # ── vitals table ─────────────────────────────────────────────────────────
        if "vitals" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("vitals")}
            new_vitals_cols = {
                "calories_burned": "FLOAT NULL COMMENT 'kcal — from Google Health'",
                "distance_km":     "FLOAT NULL COMMENT 'km — from Google Health'",
                "floors":          "INT NULL COMMENT 'floors climbed — from Google Health'",
                "active_minutes":  "INT NULL COMMENT 'active zone minutes — from Google Health'",
                "body_fat_pct":    "FLOAT NULL COMMENT '% — from smart scale'",
                "source":          "VARCHAR(50) NULL COMMENT 'google_health | station | NULL'",
            }
            for col_name, col_def in new_vitals_cols.items():
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE vitals ADD COLUMN {col_name} {col_def}"))
                    conn.commit()

        # ── recommendations table ────────────────────────────────────────────────
        if "recommendations" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("recommendations")}
            new_rec_cols = {
                "tier":        "ENUM('safety','primary_action','supporting_insight') NOT NULL DEFAULT 'primary_action'",
                "rule_id":     "VARCHAR(100) NULL",
                "evidence":    "JSON NULL",
                "action_data": "JSON NULL",
                "expires_at":  "DATETIME NULL",
            }
            for col_name, col_def in new_rec_cols.items():
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE recommendations ADD COLUMN {col_name} {col_def}"))
                    conn.commit()


# Create any new tables, then patch existing ones
Base.metadata.create_all(bind=engine)
_run_migrations()

app = FastAPI(
    title="Vita API",
    description="Backend API for the Pulse Pixel Guide (Vita) health monitoring app",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,   # separate from JWT_SECRET_KEY
    same_site="lax",
    https_only=False,   # set True in production
)

# CORS — wildcard ("*") is NOT allowed when allow_credentials=True.
# Always use explicit origins from the CORS_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.github\.io",
    allow_credentials=True,    # required for session cookies during OAuth redirect
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
app.include_router(vitals.router, prefix="/api")
app.include_router(meals.router, prefix="/api")
app.include_router(food_recognition.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(google_health.router, prefix="/api")

# Serve uploaded meal images as static files at /uploads/meals/<filename>
app.mount("/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
