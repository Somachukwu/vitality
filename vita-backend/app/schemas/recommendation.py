from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class RecommendationCreate(BaseModel):
    type: Literal["nutrition", "activity", "health_alert", "goal_progress"]
    severity: Literal["info", "warning", "critical"] = "info"
    tier: Literal["safety", "primary_action", "supporting_insight"] = "primary_action"
    rule_id: Optional[str] = None
    title: str
    message: str
    evidence: Optional[dict[str, Any]] = None
    action_data: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class RecommendationOut(BaseModel):
    id: int
    type: str
    severity: str
    tier: str = "primary_action"
    rule_id: Optional[str] = None
    title: str
    message: str
    evidence: Optional[dict[str, Any]] = None
    action_data: Optional[dict[str, Any]] = None
    is_read: bool
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RecommendationsGroupedOut(BaseModel):
    safety_alert: Optional[RecommendationOut] = None
    primary_action: Optional[RecommendationOut] = None
    supporting_insight: Optional[RecommendationOut] = None
    all_active: list[RecommendationOut] = []

