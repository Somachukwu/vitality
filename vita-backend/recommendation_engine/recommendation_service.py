"""
The entry point for generating recommendations in VITALITY.

Provides both:
1. `generate_recommendations(...)` — Pure, stateless function for testing and standalone runs.
2. `generate_and_persist_recommendations(user_id, db, ...)` — Database-connected orchestrator
   that extracts user history, runs fusion, evaluates the engine, and persists new cards.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from typing import TYPE_CHECKING, Any, Iterable, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


from .fusion import build_daily_snapshot
from .ml import detect_anomaly, detect_trends
from .models import (
    ActivityLevel,
    DailySnapshot,
    FoodLogEntry,
    Recommendation,
    Sex,
    SleepSessionReading,
    Tier,
    UserProfile,
    VitalsReading,
)
from .rules import ALL_RULES
from .rules_engine import RuleEngine

_engine = RuleEngine()
_engine.register_all(ALL_RULES)

# Maps the string stored in notification_preferences.targets.activity_level → ActivityLevel enum
_ACTIVITY_MAP: dict[str, ActivityLevel] = {
    "sedentary":  ActivityLevel.SEDENTARY,
    "light":      ActivityLevel.LIGHT,
    "moderate":   ActivityLevel.MODERATE,
    "active":     ActivityLevel.ACTIVE,
    "very_active": ActivityLevel.VERY_ACTIVE,
}


def generate_recommendations(
    profile: UserProfile,
    day: date,
    vitals: Iterable[VitalsReading] | None = None,
    food_logs: Iterable[FoodLogEntry] | None = None,
    sleep_sessions: Iterable[SleepSessionReading] | None = None,
    history: list[DailySnapshot] | None = None,
    active_cooldown_rules: set[str] | None = None,
    limit_delivery: bool = True,
) -> list[Recommendation]:
    """
    Pure-function recommendation generator.
    """
    history = history or []
    snapshot = build_daily_snapshot(
        user_profile=profile,
        day=day,
        vitals=vitals,
        food_logs=food_logs,
        sleep_sessions=sleep_sessions,
    )

    facts: dict[str, Any] = {
        "snapshot": snapshot,
        "profile": profile,
    }

    # Statistical Trend and Anomaly detection
    facts.update(detect_trends(history))
    facts.update(detect_anomaly(history, snapshot))

    return _engine.run(
        facts=facts,
        active_cooldown_rules=active_cooldown_rules,
        limit_delivery=limit_delivery,
    )


def recommendations_to_dict(recs: list[Recommendation]) -> list[dict[str, Any]]:
    """Convenience serializer for API payloads."""
    return [
        {
            "category": r.category,
            "priority": r.priority.value,
            "tier": r.tier.value,
            "title": r.title,
            "message": r.message,
            "evidence": r.evidence,
            "action_data": r.action_data,
            "rule_id": r.rule_id,
            "cooldown_days": r.cooldown_days,
            "confidence": r.confidence,
        }
        for r in recs
    ]


# ==============================================================================
# Database-Connected Orchestration
# ==============================================================================

def generate_and_persist_recommendations(
    user_id: int,
    db: Session,
    target_date: Optional[date] = None,
) -> list[Any]:
    """
    Orchestrates end-to-end recommendation generation for a live database user.
    Pulls 30-day vitals, sleep, and meal history, executes the engine,
    and commits resulting recommendations to the database.
    """
    from app.models.meal import Meal
    from app.models.recommendation import Recommendation as RecommendationModel
    from app.models.sleep_session import SleepSession
    from app.models.user import User
    from app.models.vitals import Vitals

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []

    today = target_date or datetime.now(timezone.utc).date()
    history_start = today - timedelta(days=30)
    history_start_dt = datetime.combine(history_start, datetime.min.time())

    # 1. Build UserProfile adapter
    sex_enum = Sex.FEMALE if (user.sex or "").lower() == "female" else Sex.MALE
    profile = UserProfile(
        user_id=str(user.id),
        age=user.age or 25,
        sex=sex_enum,
        height_cm=float(user.height) if user.height else 170.0,
        weight_kg=float(user.weight) if user.weight else 70.0,
        # BUG-12 FIX: activity_level is saved by the goals page into
        # notification_preferences.targets.activity_level (JSON). No DB column exists yet,
        # so we read from that JSON key and map to the ActivityLevel enum.
        activity_level=_ACTIVITY_MAP.get(
            (user.notification_preferences or {}).get("targets", {}).get("activity_level", "moderate"),
            ActivityLevel.MODERATE,
        ),
        goal=user.goal_type or "maintenance",
        target_calories=float(user.daily_calorie_target) if user.daily_calorie_target else None,
    )

    # 2. Fetch vitals, sleep, and meals
    vitals_rows = (
        db.query(Vitals)
        .filter(Vitals.user_id == user_id, Vitals.recorded_at >= history_start_dt)
        .order_by(Vitals.recorded_at.asc())
        .all()
    )

    sleep_rows = (
        db.query(SleepSession)
        .filter(SleepSession.user_id == user_id, SleepSession.sleep_date >= history_start)
        .order_by(SleepSession.sleep_date.asc())
        .all()
    )

    meal_rows = (
        db.query(Meal)
        .filter(Meal.user_id == user_id, Meal.logged_at >= history_start_dt)
        .order_by(Meal.logged_at.asc())
        .all()
    )

    # 3. Group by date to construct historical snapshots
    by_date_vitals: dict[date, list[VitalsReading]] = {}
    for r in vitals_rows:
        d = r.recorded_at.date()
        by_date_vitals.setdefault(d, []).append(
            VitalsReading(
                timestamp=r.recorded_at,
                heart_rate_bpm=r.heart_rate,
                spo2_pct=r.spo2,
                steps=r.steps,
                active_minutes=r.active_minutes,
                calories_burned=r.calories_burned,
                weight_kg=r.weight,
                temperature_c=r.temperature,
            )
        )

    by_date_sleep: dict[date, list[SleepSessionReading]] = {}
    for s in sleep_rows:
        by_date_sleep.setdefault(s.sleep_date, []).append(
            SleepSessionReading(
                sleep_date=s.sleep_date,
                sleep_start=s.sleep_start,
                sleep_end=s.sleep_end,
                duration_min=s.duration_min,
                light_min=s.light_min,
                deep_min=s.deep_min,
                rem_min=s.rem_min,
                awake_min=s.awake_min,
            )
        )

    by_date_meals: dict[date, list[FoodLogEntry]] = {}
    for m in meal_rows:
        d = m.logged_at.date()
        for item in m.items:
            by_date_meals.setdefault(d, []).append(
                FoodLogEntry(
                    timestamp=m.logged_at,
                    food_name=item.food_name,
                    calories=item.calories,
                    protein_g=item.protein,
                    carbs_g=item.carbs,
                    fat_g=item.fat,
                    portion_confidence=1.0,
                )
            )

    # Build 30-day history (excluding today) over the COMPLETE date range.
    # Previously we only included dates that had at least one data point,
    # which created gaps in the timeline. These gaps broke the consecutive-sleep
    # streak counter in trend_detection.py, preventing the sleep rule from firing.
    # Now every day in the window is included; days with no data get an empty snapshot
    # (total_sleep_hours=None, total_steps=None) which the trend detectors skip correctly.
    all_past_dates = sorted(
        history_start + timedelta(days=i)
        for i in range((today - history_start).days)
    )

    history_snapshots: list[DailySnapshot] = []
    for d in all_past_dates:
        history_snapshots.append(
            build_daily_snapshot(
                user_profile=profile,
                day=d,
                vitals=by_date_vitals.get(d, []),
                food_logs=by_date_meals.get(d, []),
                sleep_sessions=by_date_sleep.get(d, []),
            )
        )

    # 4. Check active cooldowns from DB recommendations table
    # Only recommendations from PREVIOUS days on multi-day cooldown suppress generation.
    # Today's own same-day recommendations do NOT block intraday re-evaluations when user logs meals or steps.
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start_dt = datetime.combine(today, datetime.min.time())

    recent_recs = (
        db.query(RecommendationModel)
        .filter(
            RecommendationModel.user_id == user_id,
            RecommendationModel.created_at < today_start_dt,
            RecommendationModel.created_at >= now_naive - timedelta(days=7),
        )
        .all()
    )

    cooldown_rules: set[str] = set()
    for r in recent_recs:
        if r.rule_id and r.expires_at and r.expires_at > now_naive:
            cooldown_rules.add(r.rule_id)

    # 5. Generate fresh recommendations
    todays_vitals = by_date_vitals.get(today, [])
    todays_meals = by_date_meals.get(today, [])
    todays_sleep = by_date_sleep.get(today, [])

    generated = generate_recommendations(
        profile=profile,
        day=today,
        vitals=todays_vitals,
        food_logs=todays_meals,
        sleep_sessions=todays_sleep,
        history=history_snapshots,
        active_cooldown_rules=cooldown_rules,
        limit_delivery=False,
    )

    # Curate delivery: preserve any active Safety alerts, plus top Primary Action
    # and top Supporting Insight per category (Nutrition, Activity, Vitals/Alert, Goal Progress)
    # This guarantees the user has their meal insight and step insight generated without
    # one category starving the other.
    category_actions: dict[str, Recommendation] = {}
    category_insights: dict[str, Recommendation] = {}
    safety_alerts: list[Recommendation] = []

    for rec in generated:
        if rec.tier == Tier.SAFETY:
            safety_alerts.append(rec)
        elif rec.tier == Tier.PRIMARY_ACTION:
            if rec.category not in category_actions:
                category_actions[rec.category] = rec
        elif rec.tier == Tier.SUPPORTING_INSIGHT:
            if rec.category not in category_insights:
                category_insights[rec.category] = rec

    curated_to_persist = [
        *safety_alerts,
        *category_actions.values(),
        *category_insights.values(),
    ]

    # 6. Map to database RecommendationModel and persist (or update today's live record)
    db_records: list[RecommendationModel] = []
    for rec in curated_to_persist:
        # Daily and reminder rules (cooldown_days <= 1) expire at the end of the calendar day
        # so they start fresh the next morning without multi-day suppression.
        if rec.cooldown_days <= 1:
            expires_dt = datetime.combine(today, datetime.max.time().replace(microsecond=0))
        else:
            expires_dt = datetime.combine(today + timedelta(days=rec.cooldown_days - 1), datetime.max.time().replace(microsecond=0))

        # Severity mapping
        severity_val = "info"
        if rec.priority.value in ("critical", "high"):
            severity_val = "critical" if rec.priority.value == "critical" else "warning"

        # Check if this rule_id was ALREADY generated today for this user
        existing_today = (
            db.query(RecommendationModel)
            .filter(
                RecommendationModel.user_id == user_id,
                RecommendationModel.rule_id == rec.rule_id,
                RecommendationModel.created_at >= today_start_dt,
            )
            .first()
        )
        if existing_today:
            # Update with latest intraday metrics/message rather than creating duplicate DB rows
            existing_today.title = rec.title
            existing_today.message = rec.message
            existing_today.evidence = rec.evidence
            existing_today.action_data = rec.action_data
            existing_today.severity = severity_val
            existing_today.expires_at = expires_dt
            db_records.append(existing_today)
        else:
            db_rec = RecommendationModel(
                user_id=user_id,
                type=rec.category,
                severity=severity_val,
                tier=rec.tier.value,
                rule_id=rec.rule_id,
                title=rec.title,
                message=rec.message,
                evidence=rec.evidence,
                action_data=rec.action_data,
                is_read=False,
                expires_at=expires_dt,
                created_at=now_naive,
            )
            db.add(db_rec)
            db_records.append(db_rec)

    if db_records:
        db.commit()
        for r in db_records:
            db.refresh(r)
    else:
        # If no records were inserted/updated, return today's existing records
        db_records = (
            db.query(RecommendationModel)
            .filter(
                RecommendationModel.user_id == user_id,
                RecommendationModel.created_at >= today_start_dt,
            )
            .order_by(RecommendationModel.created_at.desc())
            .all()
        )

    return db_records

