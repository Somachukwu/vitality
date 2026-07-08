"""
Anomaly detection over a user's recent history of DailySnapshots.

Design choice: Isolation Forest, unsupervised, per-user. We don't need
labeled "this was a bad day" data (which nobody has) — Isolation Forest
just learns what's "normal" for THIS user from their own recent history
and flags days that deviate. This is what makes it feasible to defend:
no external dataset, no training pipeline, works from day one of
sparse per-user data (falls back gracefully below a minimum history size).

Output is not shown to the user directly — it adds facts (e.g.
"vitals_anomaly": True) that the rule engine's correlation rules can
react to, keeping the final explanation rule-based and readable.
"""

from typing import Optional

import numpy as np

from ..models import DailySnapshot

MIN_HISTORY_FOR_ML = 10  # need at least this many prior days to train meaningfully


def _snapshot_to_vector(s: DailySnapshot) -> Optional[list]:
    """Only include a snapshot if it has enough non-null fields to be useful."""
    fields = [
        s.avg_heart_rate,
        s.resting_heart_rate,
        s.avg_spo2,
        s.total_sleep_hours,
        s.avg_stress_score,
        s.total_steps,
        s.calorie_balance,
    ]
    if sum(1 for f in fields if f is None) > 2:
        return None
    # Fill remaining Nones with 0 — Isolation Forest tolerates this fine
    # since it's per-feature and consistent across the history.
    return [f if f is not None else 0.0 for f in fields]


def detect_anomaly(history: list[DailySnapshot], today: DailySnapshot) -> dict:
    """
    Returns a facts dict, e.g. {"vitals_anomaly": True, "anomaly_score": -0.31}
    Safe to call with sparse data — returns {} if there isn't enough history.
    """
    usable_history = [v for s in history if (v := _snapshot_to_vector(s)) is not None]
    today_vec = _snapshot_to_vector(today)

    if len(usable_history) < MIN_HISTORY_FOR_ML or today_vec is None:
        return {}

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return {}

    X = np.array(usable_history)
    model = IsolationForest(n_estimators=100, contamination=0.15, random_state=42)
    model.fit(X)

    today_arr = np.array(today_vec).reshape(1, -1)
    prediction = model.predict(today_arr)[0]  # -1 = anomaly, 1 = normal
    score = float(model.decision_function(today_arr)[0])

    return {
        "vitals_anomaly": prediction == -1,
        "anomaly_score": score,
    }
