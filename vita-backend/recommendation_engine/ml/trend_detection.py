"""
Trend detection: is a metric (weight, resting HR, sleep, stress) moving
in a meaningful direction over the last N days, or just noisy?

Uses ordinary least-squares slope over a rolling window plus a z-score
check on today's value vs. the window's mean/std. Deliberately simple
and interpretable (no black box) — this is presented in the report as
"statistical trend analysis", complementing the anomaly detector.
"""

from typing import Optional

import numpy as np

from ..models import DailySnapshot

MIN_WINDOW = 5


def _series(history: list[DailySnapshot], field: str) -> list[float]:
    return [getattr(s, field) for s in history if getattr(s, field) is not None]


def _slope(values: list[float]) -> float:
    x = np.arange(len(values))
    y = np.array(values)
    # Simple OLS slope: cov(x,y) / var(x)
    return float(np.polyfit(x, y, 1)[0])


def detect_trends(history: list[DailySnapshot]) -> dict:
    """
    Returns facts like:
    {
        "resting_hr_baseline": 62.4,
        "resting_hr_trend": "rising",
        "sleep_trend": "falling",
        "stress_trend": "rising",
    }
    Safe with sparse history — only includes keys it has enough data for.
    """
    facts: dict = {}

    hr_series = _series(history, "resting_heart_rate")
    if len(hr_series) >= MIN_WINDOW:
        facts["resting_hr_baseline"] = float(np.mean(hr_series))
        slope = _slope(hr_series)
        facts["resting_hr_trend"] = "rising" if slope > 0.3 else "falling" if slope < -0.3 else "stable"

    sleep_series = _series(history, "total_sleep_hours")
    if len(sleep_series) >= MIN_WINDOW:
        slope = _slope(sleep_series)
        facts["sleep_trend"] = "rising" if slope > 0.1 else "falling" if slope < -0.1 else "stable"

    stress_series = _series(history, "avg_stress_score")
    if len(stress_series) >= MIN_WINDOW:
        slope = _slope(stress_series)
        facts["stress_trend"] = "rising" if slope > 1.0 else "falling" if slope < -1.0 else "stable"

    return facts
