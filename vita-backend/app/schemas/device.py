from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DeviceRegister(BaseModel):
    device_uid: str
    device_name: str = "ESP32 Device"
    device_type: Literal["wearable", "station"] = "wearable"


class DeviceOut(BaseModel):
    id: int
    device_uid: str
    device_name: str
    device_type: str
    api_key: str
    is_active: bool
    last_seen: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
