"""
Anomaly detection over a user's recent history of DailySnapshots.

Uses an unsupervised Isolation Forest trained on the user's own dense history
to flag statistical multivariate anomalies (e.g. sudden drop in sleep + spike in HR)
without diagnostic claims.
"""

from typing import Optional
import numpy as np

from ..models import DailySnapshot

MIN_HISTORY_FOR_ML = 10


def _extract_raw_features(s: DailySnapshot) -> list[Optional[float]]:
    return [
        s.avg_heart_rate,
        s.resting_heart_rate,
        s.avg_spo2,
        s.total_sleep_hours,
        s.total_steps,
        s.total_calories,
    ]


def detect_anomaly(history: list[DailySnapshot], today: DailySnapshot) -> dict:
    """
    Returns a facts dict, e.g. {"vitals_anomaly": True, "anomaly_score": -0.31}
    Safe with sparse history — returns {} if there isn't enough history.
    """
    if len(history) < MIN_HISTORY_FOR_ML:
        return {}

    raw_matrix = [_extract_raw_features(s) for s in history]
    today_raw = _extract_raw_features(today)

    # Filter out days with >2 missing features
    valid_rows = [row for row in raw_matrix if sum(1 for v in row if v is None) <= 2]
    if len(valid_rows) < MIN_HISTORY_FOR_ML or sum(1 for v in today_raw if v is None) > 2:
        return {}

    # Compute column means for safe imputation instead of 0.0
    cols_count = len(today_raw)
    col_means = []
    for col_idx in range(cols_count):
        vals = [r[col_idx] for r in valid_rows if r[col_idx] is not None]
        col_means.append(float(np.mean(vals)) if vals else 0.0)

    # Impute missing values with column means
    X = np.array([[r[c] if r[c] is not None else col_means[c] for c in range(cols_count)] for r in valid_rows])
    today_vec = np.array([today_raw[c] if today_raw[c] is not None else col_means[c] for c in range(cols_count)]).reshape(1, -1)

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return {}

    model = IsolationForest(n_estimators=50, contamination=0.15, random_state=42)
    model.fit(X)

    prediction = model.predict(today_vec)[0]  # -1 = anomaly, 1 = normal
    score = float(model.decision_function(today_vec)[0])

    return {
        "vitals_anomaly": bool(prediction == -1),
        "anomaly_score": round(score, 3),
    }

