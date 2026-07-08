"""
Fusion layer: combines Fitbit vitals readings + CV food log entries
+ user profile into a single DailySnapshot per day.

This is intentionally pure-function / stateless — pass it lists,
get a snapshot back. Your backend handles fetching from Fitbit's API
and your DB; this module never talks to Fitbit or the DB directly.
"""

from datetime import date
from statistics import mean
from typing import Iterable

from .models import (
    ActivityLevel,
    DailySnapshot,
    FoodLogEntry,
    Sex,
    UserProfile,
    VitalsReading,
)


def estimate_bmr(profile: UserProfile) -> float:
    """Mifflin-St Jeor equation."""
    if profile.sex == Sex.MALE:
        return 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age + 5
    return 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age - 161


_ACTIVITY_MULTIPLIER = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.9,
}


def estimate_calorie_target(profile: UserProfile) -> float:
    if profile.target_calories:
        return profile.target_calories
    tdee = estimate_bmr(profile) * _ACTIVITY_MULTIPLIER[profile.activity_level]
    if profile.goal == "lose":
        return tdee - 500
    if profile.goal == "gain":
        return tdee + 300
    return tdee


def build_daily_snapshot(
    user_profile: UserProfile,
    day: date,
    vitals: Iterable[VitalsReading],
    food_logs: Iterable[FoodLogEntry],
) -> DailySnapshot:
    vitals = list(vitals)
    food_logs = list(food_logs)

    hr_values = [v.heart_rate_bpm for v in vitals if v.heart_rate_bpm is not None]
    spo2_values = [v.spo2_pct for v in vitals if v.spo2_pct is not None]
    temp_values = [v.skin_temp_deviation_c for v in vitals if v.skin_temp_deviation_c is not None]
    stress_values = [v.stress_score for v in vitals if v.stress_score is not None]
    sleep_minutes = sum(v.sleep_minutes or 0 for v in vitals)
    steps_total = sum(v.steps or 0 for v in vitals)

    # Resting HR approximated as the 10th-percentile of HR readings for the day
    resting_hr = None
    if hr_values:
        sorted_hr = sorted(hr_values)
        idx = max(0, int(len(sorted_hr) * 0.1) - 1)
        resting_hr = sorted_hr[idx]

    calorie_target = estimate_calorie_target(user_profile)
    total_calories = sum(f.calories for f in food_logs)

    return DailySnapshot(
        user_id=user_profile.user_id,
        day=day,
        avg_heart_rate=mean(hr_values) if hr_values else None,
        resting_heart_rate=resting_hr,
        avg_spo2=mean(spo2_values) if spo2_values else None,
        avg_skin_temp_deviation=mean(temp_values) if temp_values else None,
        total_steps=steps_total,
        avg_stress_score=mean(stress_values) if stress_values else None,
        total_sleep_hours=sleep_minutes / 60 if sleep_minutes else None,
        total_calories=total_calories,
        total_protein_g=sum(f.protein_g for f in food_logs),
        total_carbs_g=sum(f.carbs_g for f in food_logs),
        total_fat_g=sum(f.fat_g for f in food_logs),
        calorie_target=calorie_target,
        calorie_balance=total_calories - calorie_target if food_logs else None,
        meals_logged=len(food_logs),
    )
