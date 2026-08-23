from datetime import datetime

from pydantic import BaseModel


class GoogleHealthStatusOut(BaseModel):
    """Returned by GET /api/auth/google/status"""
    connected: bool
    google_email: str | None = None
    last_synced_at: datetime | None = None

    model_config = {"from_attributes": True}


class GoogleHealthSyncOut(BaseModel):
    """Returned by POST /api/auth/google/sync"""
    synced_count: int
    sleep_sessions_synced: int
    message: str
