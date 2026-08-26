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
    """Background task: pre-warm food recognition AI model in RAM without blocking server boot."""
    def _warmup():
        try:
            from food_cv.inference import _load_model
            _load_model()
            print("INFO: Food recognition AI model pre-warmed in RAM.")
        except Exception as exc:
            print("NOTICE: Food recognition model warmup skipped:", exc)

    await asyncio.to_thread(_warmup)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm AI model asynchronously on startup so first request has zero cold-start delay
    asyncio.create_task(_warmup_model_task())
    yield


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
_uploads_dir = Path(__file__).parent.parent / "uploads"
_uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
