from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.models import Device, Meal, MealItem, Recommendation, User, Vitals  # noqa: F401 — ensures all tables are registered
from app.routers import auth, devices, food_recognition, meals, recommendations, users, vitals


def _run_migrations():
    """Apply schema changes to existing tables that create_all() cannot handle."""
    inspector = inspect(engine)
    with engine.connect() as conn:
        # Add device_type column if this is an existing database
        if "devices" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("devices")}
            if "device_type" not in cols:
                conn.execute(text(
                    "ALTER TABLE devices ADD COLUMN device_type "
                    "ENUM('wearable','station') NOT NULL DEFAULT 'wearable'"
                ))
                conn.commit()


# Create any new tables, then patch existing ones
Base.metadata.create_all(bind=engine)
_run_migrations()

app = FastAPI(
    title="Vita API",
    description="Backend API for the Pulse Pixel Guide (Vita) health monitoring app",
    version="1.0.0",
)

_cors_origins = ["*"] if settings.APP_ENV == "development" else settings.cors_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
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

# Serve uploaded meal images as static files at /uploads/meals/<filename>
_uploads_dir = Path(__file__).parent.parent / "uploads"
_uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
