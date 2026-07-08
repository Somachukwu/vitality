"""
The single entry point your Flask/FastAPI route should call.

    from recommendation_engine.recommendation_service import generate_recommendations

    recs = generate_recommendations(
        profile=user_profile,
        day=today,
        vitals=todays_vitals_readings,
        food_logs=todays_food_logs,
        history=last_30_days_of_snapshots,   # list[DailySnapshot], most recent last
    )

`history` should NOT include today — it's the prior days used to give
the ML layer something to compare against. Your backend is responsible
for building/caching these DailySnapshots (e.g. one per user per day,
computed once vitals+food data for that day is finalized) and storing
them so you're not recomputing 30 days of fusion on every request.
"""

from datetime import date
from typing import Iterable

from .fusion import build_daily_snapshot
from .ml import detect_anomaly, detect_trends
from .models import DailySnapshot, FoodLogEntry, Recommendation, UserProfile, VitalsReading
from .rules import ALL_RULES
from .rules_engine import RuleEngine

_engine = RuleEngine()
_engine.register_all(ALL_RULES)


def generate_recommendations(
    profile: UserProfile,
    day: date,
    vitals: Iterable[VitalsReading],
    food_logs: Iterable[FoodLogEntry],
    history: list[DailySnapshot] | None = None,
) -> list[Recommendation]:
    history = history or []

    snapshot = build_daily_snapshot(profile, day, vitals, food_logs)

    facts: dict = {
        "snapshot": snapshot,
        "profile": profile,
    }

    # ML layer adds facts; rules never call sklearn directly.
    facts.update(detect_trends(history))
    facts.update(detect_anomaly(history, snapshot))

    return _engine.run(facts)


def recommendations_to_dict(recs: list[Recommendation]) -> list[dict]:
    """Convenience serializer for your API layer."""
    return [
        {
            "category": r.category,
            "priority": r.priority.value,
            "title": r.title,
            "message": r.message,
            "evidence": r.evidence,
            "rule_id": r.rule_id,
        }
        for r in recs
    ]
