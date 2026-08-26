"""
Trend detection: extracts statistical trends and rolling averages
over a user's recent history of DailySnapshots.

Calculates:
- 14-day weight slope (kg / week)
- 7-day average steps & activity volume
- Consecutive short-sleep streak
- Resting heart rate baseline
- Rolling caloric balance
"""

from typing import Any, Optional
import numpy as np

from ..models import DailySnapshot

MIN_WINDOW = 3


def _series(history: list[DailySnapshot], field: str) -> list[float]:
    return [float(getattr(s, field)) for s in history if getattr(s, field) is not None]


def _slope(values: list[float]) -> float:
    """Computes ordinary least-squares slope (rate of change per day)."""
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values))
    y = np.array(values, dtype=float)
    # cov(x,y) / var(x)
    return float(np.polyfit(x, y, 1)[0])


def detect_trends(history: list[DailySnapshot]) -> dict[str, Any]:
    """
    Returns a facts dict for the rule engine.
    Handles sparse history gracefully.
    """
    facts: dict[str, Any] = {}
    if not history:
        return facts

    # --- 1. Weight Trend (14–30 Day Window) ---
    weight_series = _series(history, "weight_kg")
    if len(weight_series) >= 3:
        facts["weight_baseline"] = round(float(np.mean(weight_series)), 2)
        facts["weight_readings_count"] = len(weight_series)
        daily_slope = _slope(weight_series)
        weekly_slope = round(daily_slope * 7.0, 2)  # kg change per week
        facts["weight_slope_kg_week"] = weekly_slope
        if weekly_slope > 0.15:
            facts["weight_trend"] = "gaining"
        elif weekly_slope < -0.15:
            facts["weight_trend"] = "losing"
        else:
            facts["weight_trend"] = "stable"

    # --- 2. Step / Activity Trend (Last 7 Days) ---
    last_7 = history[-7:] if len(history) >= 7 else history
    step_values = [s.total_steps for s in last_7 if s.total_steps is not None]
    if step_values:
        facts["weekly_avg_steps"] = int(np.mean(step_values))
        facts["step_days_count"] = len(step_values)

    # --- 3. Sleep Trend & Consecutive Short Sleep ---
    sleep_values = [s.total_sleep_hours for s in history if s.total_sleep_hours is not None]
    if sleep_values:
        facts["recent_avg_sleep_hours"] = round(float(np.mean(sleep_values[-7:])), 2)
        # Check consecutive short sleep days looking backwards from most recent
        consecutive_short = 0
        for s in reversed(history):
            if s.total_sleep_hours is not None and s.total_sleep_hours < 6.0:
                consecutive_short += 1
            elif s.total_sleep_hours is not None:
                break
        facts["consecutive_short_sleep_days"] = consecutive_short

    # --- 4. Resting Heart Rate Baseline ---
    hr_series = _series(history, "resting_heart_rate")
    if len(hr_series) >= 3:
        facts["resting_hr_baseline"] = round(float(np.mean(hr_series)), 1)
        slope = _slope(hr_series)
        facts["resting_hr_trend"] = "rising" if slope > 0.3 else "falling" if slope < -0.3 else "stable"

    # --- 5. Caloric Balance Trend ---
    balance_series = _series(history, "calorie_balance")
    if balance_series:
        facts["avg_calorie_balance"] = round(float(np.mean(balance_series)), 1)

    return facts

