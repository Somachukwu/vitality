"""
Core data models for the Vitality recommendation engine.

These are plain dataclasses so the engine has zero ORM coupling —
your Flask/FastAPI layer is responsible for mapping DB rows / Google Health
JSON / CV output into these shapes before calling the engine.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tier(str, Enum):
    SAFETY = "safety"
    PRIMARY_ACTION = "primary_action"
    SUPPORTING_INSIGHT = "supporting_insight"


class Category(str, Enum):
    NUTRITION = "nutrition"
    ACTIVITY = "activity"
    HEALTH_ALERT = "health_alert"
    GOAL_PROGRESS = "goal_progress"


@dataclass
class UserProfile:
    user_id: str
    age: int = 25
    sex: Sex = Sex.MALE
    height_cm: float = 170.0
    weight_kg: float = 70.0
    activity_level: ActivityLevel = ActivityLevel.MODERATE
    goal: str = "maintain"  # "lose", "gain", "maintain" or "weight_loss", "weight_gain", "maintenance"
    target_calories: Optional[float] = None  # override, else BMR-derived

    @property
    def normalized_goal(self) -> str:
        g = (self.goal or "").lower()
        if g in ("lose", "weight_loss", "fat_loss"):
            return "lose"
        if g in ("gain", "weight_gain", "muscle_gain"):
            return "gain"
        return "maintain"


@dataclass
class VitalsReading:
    """One wearable or sensor reading."""
    timestamp: datetime
    heart_rate_bpm: Optional[float] = None
    spo2_pct: Optional[float] = None
    steps: Optional[int] = None
    active_minutes: Optional[int] = None
    calories_burned: Optional[float] = None
    weight_kg: Optional[float] = None
    temperature_c: Optional[float] = None
    stress_score: Optional[float] = None
    hrv_ms: Optional[float] = None


@dataclass
class SleepSessionReading:
    """One sleep session recorded by wearable/Google Health."""
    sleep_date: date
    sleep_start: Optional[datetime] = None
    sleep_end: Optional[datetime] = None
    duration_min: Optional[int] = None
    light_min: Optional[int] = None
    deep_min: Optional[int] = None
    rem_min: Optional[int] = None
    awake_min: Optional[int] = None


@dataclass
class FoodLogEntry:
    """One meal, as produced by the CV recognition module or manual entry."""
    timestamp: datetime
    food_name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    portion_confidence: float = 1.0  # CV model's confidence in the portion estimate


@dataclass
class DailySnapshot:
    """The fused, aggregated picture of one user-day."""
    user_id: str
    day: date
    avg_heart_rate: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    avg_spo2: Optional[float] = None
    min_spo2: Optional[float] = None
    total_steps: int = 0
    active_minutes: int = 0
    weight_kg: Optional[float] = None
    total_sleep_hours: Optional[float] = None
    sleep_stages: dict[str, int] = field(default_factory=dict)
    total_calories: float = 0.0
    total_protein_g: float = 0.0
    total_carbs_g: float = 0.0
    total_fat_g: float = 0.0
    calorie_target: Optional[float] = None
    calorie_balance: Optional[float] = None  # intake - target; +ve = surplus
    meals_logged: int = 0
    avg_portion_confidence: float = 1.0


@dataclass
class Recommendation:
    category: str  # "nutrition" | "activity" | "health_alert" | "goal_progress"
    priority: Priority
    tier: Tier = Tier.PRIMARY_ACTION
    title: str = ""
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    action_data: Optional[dict[str, Any]] = None
    rule_id: str = ""
    cooldown_days: int = 1
    confidence: float = 1.0

