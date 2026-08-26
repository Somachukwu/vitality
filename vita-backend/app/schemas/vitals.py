from datetime import date, datetime

from pydantic import BaseModel


class VitalsIngest(BaseModel):
    """Payload sent by the ESP32 device."""
    heart_rate: float | None = None
    spo2: float | None = None
    temperature: float | None = None
    humidity: float | None = None
    weight: float | None = None
    steps: int | None = None
    recorded_at: datetime | None = None  # ESP32 can send its own timestamp; falls back to server time


class VitalsOut(BaseModel):
    id: int
    heart_rate: float | None
    spo2: float | None
    temperature: float | None
    humidity: float | None
    weight: float | None
    steps: int | None
    calories_burned: float | None = None
    distance_km: float | None = None
    floors: int | None = None
    active_minutes: int | None = None
    body_fat_pct: float | None = None
    source: str | None = None
    recorded_at: datetime

    model_config = {"from_attributes": True}


class VitalsLatestOut(VitalsOut):
    device_name: str | None = None
    last_google_sync: datetime | None = None


class VitalsDailySummary(BaseModel):
    """One row per calendar date — used by the history endpoint."""
    date: date
    # Point-in-time vitals (latest reading on that date)
    heart_rate: float | None = None
    spo2: float | None = None
    temperature: float | None = None
    weight: float | None = None
    # Daily aggregates (summed / maxed across all sources on that date)
    steps: int | None = None
    calories_burned: float | None = None
    distance_km: float | None = None
    active_minutes: int | None = None


class SyncAllOut(BaseModel):
    """Response from POST /vitals/sync-all."""
    google_synced: bool = False
    synced_count: int = 0
    sleep_sessions_synced: int = 0
    # The latest vitals are embedded so the frontend doesn't need a second request
    vitals: VitalsLatestOut | None = None
