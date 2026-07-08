from datetime import datetime

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
    recorded_at: datetime

    model_config = {"from_attributes": True}


class VitalsLatestOut(VitalsOut):
    device_name: str | None = None
