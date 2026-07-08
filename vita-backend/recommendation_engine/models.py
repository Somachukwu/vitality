"""
Core data models for the Vitality recommendation engine.

These are plain dataclasses so the engine has zero ORM coupling —
your Flask/FastAPI layer is responsible for mapping DB rows / Fitbit
JSON / CV output into these shapes before calling the engine.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"


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


@dataclass
class UserProfile:
    user_id: str
    age: int
    sex: Sex
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    goal: str = "maintain"  # "lose", "gain", "maintain"
    target_calories: Optional[float] = None  # override, else BMR-derived


@dataclass
class VitalsReading:
    """One Fitbit intraday-derived reading, already aggregated to a
    convenient granularity (e.g. hourly) by your fusion/ingestion code."""
    timestamp: datetime
    heart_rate_bpm: Optional[float] = None
    spo2_pct: Optional[float] = None
    skin_temp_deviation_c: Optional[float] = None  # deviation from baseline, NOT absolute
    steps: Optional[int] = None
    stress_score: Optional[float] = None  # Fitbit cEDA-derived, 0-100
    sleep_minutes: Optional[float] = None
    hrv_ms: Optional[float] = None


@dataclass
class FoodLogEntry:
    """One meal, as produced by the CV recognition module."""
    timestamp: datetime
    food_name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    portion_confidence: float = 1.0  # CV model's confidence in the portion estimate


@dataclass
class DailySnapshot:
    """The fused, aggregated picture of one user-day. This is what the
    ML layer and rule engine actually operate on."""
    user_id: str
    day: date
    avg_heart_rate: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    avg_spo2: Optional[float] = None
    avg_skin_temp_deviation: Optional[float] = None
    total_steps: int = 0
    avg_stress_score: Optional[float] = None
    total_sleep_hours: Optional[float] = None
    total_calories: float = 0.0
    total_protein_g: float = 0.0
    total_carbs_g: float = 0.0
    total_fat_g: float = 0.0
    calorie_target: Optional[float] = None
    calorie_balance: Optional[float] = None  # intake - target; +ve = surplus
    meals_logged: int = 0


@dataclass
class Recommendation:
    category: str          # "nutrition" | "vitals" | "correlation" | "ml_pattern"
    priority: Priority
    title: str
    message: str
    evidence: dict = field(default_factory=dict)  # the facts that triggered it
    rule_id: str = ""
