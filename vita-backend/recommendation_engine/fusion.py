"""
Fusion layer: combines Google Health vitals readings + sleep sessions
+ CV food log entries + user profile into a single DailySnapshot per day.

This is pure-function / stateless — pass it lists/iterables,
get a validated snapshot back.
"""

from datetime import date
from statistics import mean
from typing import Iterable, Optional

from .models import (
    ActivityLevel,
    DailySnapshot,
    FoodLogEntry,
    Sex,
    SleepSessionReading,
    UserProfile,
    VitalsReading,
)


def estimate_bmr(profile: UserProfile) -> float:
    """Mifflin-St Jeor equation."""
    weight = profile.weight_kg or 70.0
    height = profile.height_cm or 170.0
    age = profile.age or 25

    if profile.sex == Sex.FEMALE:
        return 10.0 * weight + 6.25 * height - 5.0 * age - 161.0
    # MALE or OTHER
    return 10.0 * weight + 6.25 * height - 5.0 * age + 5.0


_ACTIVITY_MULTIPLIER = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.9,
}


def estimate_calorie_target(profile: UserProfile) -> float:
    """Computes daily caloric target with clinical safety floors."""
    if profile.target_calories:
        return float(profile.target_calories)

    activity_level = profile.activity_level or ActivityLevel.MODERATE
    multiplier = _ACTIVITY_MULTIPLIER.get(activity_level, 1.55)
    tdee = estimate_bmr(profile) * multiplier

    goal = profile.normalized_goal
    if goal == "lose":
        target = tdee - 500.0
        # Clinical safety floor: 1200 kcal for females, 1500 kcal for males
        floor = 1200.0 if profile.sex == Sex.FEMALE else 1500.0
        return max(target, floor)
    elif goal == "gain":
        return tdee + 300.0

    return tdee


def build_daily_snapshot(
    user_profile: UserProfile,
    day: date,
    vitals: Iterable[VitalsReading] | None = None,
    food_logs: Iterable[FoodLogEntry] | None = None,
    sleep_sessions: Iterable[SleepSessionReading] | None = None,
) -> DailySnapshot:
    vitals_list = list(vitals or [])
    food_list = list(food_logs or [])
    sleep_list = list(sleep_sessions or [])

    # --- 1. Vitals Aggregation ---
    hr_values = [v.heart_rate_bpm for v in vitals_list if v.heart_rate_bpm is not None]
    spo2_values = [v.spo2_pct for v in vitals_list if v.spo2_pct is not None]
    weight_values = [v.weight_kg for v in vitals_list if v.weight_kg is not None]
    steps_total = sum(v.steps or 0 for v in vitals_list)
    active_minutes_total = sum(v.active_minutes or 0 for v in vitals_list)

    # Resting HR approximated as 10th percentile of daytime HR readings
    resting_hr = None
    if hr_values:
        sorted_hr = sorted(hr_values)
        idx = max(0, int(len(sorted_hr) * 0.1) - 1)
        resting_hr = sorted_hr[idx]

    latest_weight = weight_values[-1] if weight_values else user_profile.weight_kg

    # --- 2. Sleep Aggregation ---
    total_sleep_hours: Optional[float] = None
    sleep_stages: dict[str, int] = {}
    if sleep_list:
        total_minutes = sum(s.duration_min or 0 for s in sleep_list)
        total_sleep_hours = round(total_minutes / 60.0, 2)
        sleep_stages = {
            "light_min": sum(s.light_min or 0 for s in sleep_list),
            "deep_min": sum(s.deep_min or 0 for s in sleep_list),
            "rem_min": sum(s.rem_min or 0 for s in sleep_list),
            "awake_min": sum(s.awake_min or 0 for s in sleep_list),
        }

    # --- 3. Food / Nutrition Aggregation ---
    total_calories = sum(f.calories for f in food_list)
    total_protein = sum(f.protein_g for f in food_list)
    total_carbs = sum(f.carbs_g for f in food_list)
    total_fat = sum(f.fat_g for f in food_list)
    confidences = [f.portion_confidence for f in food_list if f.portion_confidence is not None]
    avg_confidence = mean(confidences) if confidences else 1.0

    calorie_target = estimate_calorie_target(user_profile)

    return DailySnapshot(
        user_id=user_profile.user_id,
        day=day,
        avg_heart_rate=round(mean(hr_values), 1) if hr_values else None,
        resting_heart_rate=round(resting_hr, 1) if resting_hr else None,
        avg_spo2=round(mean(spo2_values), 1) if spo2_values else None,
        min_spo2=round(min(spo2_values), 1) if spo2_values else None,
        total_steps=steps_total,
        active_minutes=active_minutes_total,
        weight_kg=round(latest_weight, 2) if latest_weight else None,
        total_sleep_hours=total_sleep_hours,
        sleep_stages=sleep_stages,
        total_calories=round(total_calories, 1),
        total_protein_g=round(total_protein, 1),
        total_carbs_g=round(total_carbs, 1),
        total_fat_g=round(total_fat, 1),
        calorie_target=round(calorie_target, 1),
        calorie_balance=round(total_calories - calorie_target, 1) if food_list else None,
        meals_logged=len(food_list),
        avg_portion_confidence=round(avg_confidence, 2),
    )

