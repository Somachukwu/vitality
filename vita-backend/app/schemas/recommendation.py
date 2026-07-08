from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RecommendationCreate(BaseModel):
    type: Literal["nutrition", "activity", "health_alert", "goal_progress"]
    severity: Literal["info", "warning", "critical"] = "info"
    title: str
    message: str


class RecommendationOut(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
