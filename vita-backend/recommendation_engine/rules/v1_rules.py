"""
V1 Core Rules and Safety Gate for the VITALITY Recommendation Engine.

Every rule is a pure function taking a facts dictionary and returning
a strongly-typed Recommendation object with complete audit evidence.
"""

from typing import Any

from ..models import Category, DailySnapshot, Priority, Recommendation, Tier, UserProfile
from ..rules_engine import Rule


def _snapshot(facts: dict[str, Any]) -> DailySnapshot:
    return facts["snapshot"]


def _profile(facts: dict[str, Any]) -> UserProfile:
    return facts["profile"]


# ==============================================================================
# 1. SAFETY GATE RULES (Highest Precedence — Tier: SAFETY)
# ==============================================================================

def _rule_safety_critical_spo2_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    val = s.min_spo2 if s.min_spo2 is not None else s.avg_spo2
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.CRITICAL,
        tier=Tier.SAFETY,
        rule_id="safety.critical_spo2",
        title="Low Blood Oxygen Reading",
        message=(
            f"Your blood oxygen level was recorded at {val:.1f}%, which is below the normal "
            "resting threshold (95-100%). If you experience shortness of breath, dizziness, "
            "or chest discomfort, please seek medical evaluation."
        ),
        evidence={"recorded_spo2": val, "threshold": 90.0},
        action_data={"action_type": "clinical_notice", "dismissable": True},
        cooldown_days=1,
        confidence=1.0,
    )


def _rule_safety_severe_deficit_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.HIGH,
        tier=Tier.SAFETY,
        rule_id="safety.severe_deficit",
        title="Severe Calorie Deficit",
        message=(
            f"Your logged energy intake today is {s.total_calories:.0f} kcal against a target of "
            f"{s.calorie_target:.0f} kcal (a deficit of {abs(s.calorie_balance or 0):.0f} kcal). "
            "Extended extreme calorie deficits can impair recovery, metabolism, and immune function."
        ),
        evidence={"total_calories": s.total_calories, "target": s.calorie_target, "deficit": abs(s.calorie_balance or 0)},
        action_data={"action_type": "nutrition_warning", "route": "food-log.html"},
        cooldown_days=1,
        confidence=0.9,
    )


SAFETY_RULES = [
    Rule(
        rule_id="safety.critical_spo2",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.SAFETY,
        condition=lambda f: (
            _snapshot(f).min_spo2 is not None and _snapshot(f).min_spo2 < 90.0
            or (_snapshot(f).avg_spo2 is not None and _snapshot(f).avg_spo2 < 90.0)
        ),
        action=_rule_safety_critical_spo2_action,
        weight=100,
        cooldown_days=1,
    ),
    Rule(
        rule_id="safety.severe_deficit",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.SAFETY,
        condition=lambda f: (
            _snapshot(f).meals_logged >= 2
            and _snapshot(f).calorie_target is not None
            and _snapshot(f).calorie_balance is not None
            and (_snapshot(f).total_calories < 1000 or _snapshot(f).calorie_balance < -1200)
        ),
        action=_rule_safety_severe_deficit_action,
        weight=90,
        cooldown_days=1,
    ),
]


# ==============================================================================
# 2. CORE V1 RULES (Primary Actions & Supporting Insights)
# ==============================================================================

# --- Rule 1: Incomplete Meal Logging (Primary Action) ---
def _rule_incomplete_meal_logging_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    if s.meals_logged == 0:
        msg = "You haven't logged any meals today. Take a quick photo of your meals to keep your daily calorie and macro tracking accurate."
    else:
        msg = f"You have logged {s.meals_logged} meal(s) today (~{s.total_calories:.0f} kcal). Log your remaining meals to keep your nutrition targets on track."
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="nutrition.incomplete_logging",
        title="Complete Your Daily Meal Log",
        message=msg,
        evidence={"meals_logged": s.meals_logged, "total_calories": s.total_calories, "target_calories": s.calorie_target},
        action_data={"action_label": "Log Meal", "route": "food-log.html"},
        cooldown_days=1,
        confidence=1.0,
    )


# --- Rule 2: Persistent Short Sleep (Primary Action / Insight) ---
def _rule_persistent_short_sleep_action(facts: dict[str, Any]) -> Recommendation:
    consecutive_days = facts.get("consecutive_short_sleep_days", 3)
    avg_sleep = facts.get("recent_avg_sleep_hours", 5.5)
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.HIGH,
        tier=Tier.PRIMARY_ACTION,
        rule_id="vitals.persistent_short_sleep",
        title="Cumulative Sleep Debt",
        message=(
            f"You have slept under 6 hours for {consecutive_days} consecutive nights "
            f"(averaging {avg_sleep:.1f} hrs). Consecutive short sleep elevates cortisol and "
            "impairs recovery. Prioritize an earlier bedtime tonight."
        ),
        evidence={"consecutive_short_days": consecutive_days, "recent_avg_hours": avg_sleep},
        action_data={"action_label": "Sleep Tips", "route": "profile.html"},
        cooldown_days=3,
        confidence=0.95,
    )


# --- Rule 3: Weekly Activity Gap (Primary Action) ---
def _rule_weekly_step_gap_action(facts: dict[str, Any]) -> Recommendation:
    weekly_avg = facts.get("weekly_avg_steps", 4000)
    return Recommendation(
        category=Category.ACTIVITY.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="activity.weekly_step_gap",
        title="Increase Daily Activity",
        message=(
            f"Your daily steps over the past week have averaged {weekly_avg:,} steps/day, "
            "which is below the healthy baseline (7,000-10,000 steps). A 20-30 minute brisk walk "
            "today will help close this gap."
        ),
        evidence={"weekly_avg_steps": weekly_avg, "target_baseline": 8000},
        action_data={"action_label": "Track Activity", "route": "vitals.html"},
        cooldown_days=4,
        confidence=0.9,
    )


# --- Rule 4: Nutrition Quality Gap - Protein (Supporting Insight) ---
def _rule_protein_quality_gap_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    p = _profile(facts)
    weight = p.weight_kg or 70.0
    target_protein = round(weight * 1.2, 0)
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.LOW,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="nutrition.protein_quality_gap",
        title="Protein Target Alignment",
        message=(
            f"Your protein intake today is {s.total_protein_g:.0f}g. For your weight ({weight:.0f}kg), "
            f"aiming for around {target_protein:.0f}g supports satiety and lean muscle preservation."
        ),
        evidence={"total_protein_g": s.total_protein_g, "target_protein_g": target_protein, "weight_kg": weight},
        action_data={"action_label": "View Nutrition", "route": "food-log.html"},
        cooldown_days=2,
        confidence=0.85,
    )


# --- Rule 5: Weight-Goal Trend Mismatch (Supporting Insight) ---
def _rule_weight_trend_mismatch_action(facts: dict[str, Any]) -> Recommendation:
    p = _profile(facts)
    slope = facts.get("weight_slope_kg_week", 0.0)
    balance = facts.get("avg_calorie_balance", 0.0)
    goal = p.normalized_goal

    if goal == "lose":
        title = "Weight Trend Above Target"
        message = (
            f"Over the last 2-4 weeks, your weight has trended upward by ~{slope:+.2f} kg/week "
            f"with an average daily calorie surplus of {balance:+.0f} kcal. Adjusting portion sizes "
            "slightly will help align with your weight loss goal."
        )
    else:
        title = "Weight Trend Below Target"
        message = (
            f"Your weight has trended downward by ~{slope:.2f} kg/week, which is below your weight gain "
            "target. Adding nutrient-dense snacks will help support your goal."
        )

    return Recommendation(
        category=Category.GOAL_PROGRESS.value,
        priority=Priority.MEDIUM,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="goal.weight_trend_mismatch",
        title=title,
        message=message,
        evidence={"weight_slope_kg_week": slope, "avg_calorie_balance": balance, "goal": goal},
        action_data={"action_label": "Adjust Goals", "route": "profile.html"},
        cooldown_days=7,
        confidence=0.9,
    )


# --- Supporting Insight: Elevated Resting HR ---
def _rule_elevated_resting_hr_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    baseline = facts.get("resting_hr_baseline", 65.0)
    rhr = s.resting_heart_rate or 75.0
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.LOW,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="vitals.elevated_resting_hr",
        title="Elevated Resting Heart Rate",
        message=(
            f"Resting heart rate today (~{rhr:.0f} bpm) is elevated above your recent baseline (~{baseline:.0f} bpm). "
            "This can reflect incomplete recovery, mild stress, or poor sleep. An easier day of physical activity is recommended."
        ),
        evidence={"resting_heart_rate": rhr, "baseline": baseline, "delta": round(rhr - baseline, 1)},
        action_data={"action_label": "View Vitals", "route": "vitals.html"},
        cooldown_days=2,
        confidence=0.85,
    )



V1_RULES = [
    # 1. Incomplete Meal Logging
    Rule(
        rule_id="nutrition.incomplete_logging",
        category=Category.NUTRITION.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            _profile(f).target_calories is not None
            and (
                _snapshot(f).meals_logged == 0
                or (
                    _snapshot(f).meals_logged in (1, 2)
                    and _snapshot(f).calorie_target is not None
                    and _snapshot(f).total_calories < (_snapshot(f).calorie_target * 0.65)
                )
            )
        ),
        action=_rule_incomplete_meal_logging_action,
        weight=80,
        cooldown_days=1,
    ),
    # 2. Persistent Short Sleep
    Rule(
        rule_id="vitals.persistent_short_sleep",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: facts_short_sleep(f),
        action=_rule_persistent_short_sleep_action,
        weight=75,
        cooldown_days=3,
    ),
    # 3. Weekly Step Gap
    Rule(
        rule_id="activity.weekly_step_gap",
        category=Category.ACTIVITY.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            f.get("weekly_avg_steps") is not None
            and f.get("step_days_count", 0) >= 3
            and f["weekly_avg_steps"] < 5500
        ),
        action=_rule_weekly_step_gap_action,
        weight=65,
        cooldown_days=4,
    ),
    # 4. Nutrition Quality Gap - Protein
    Rule(
        rule_id="nutrition.protein_quality_gap",
        category=Category.NUTRITION.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            _snapshot(f).meals_logged >= 2
            and _snapshot(f).total_protein_g > 0
            and _snapshot(f).total_protein_g < (_profile(f).weight_kg or 70.0) * 0.85
        ),
        action=_rule_protein_quality_gap_action,
        weight=50,
        cooldown_days=2,
    ),
    # 5. Weight Trend vs Goal Mismatch
    Rule(
        rule_id="goal.weight_trend_mismatch",
        category=Category.GOAL_PROGRESS.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            f.get("weight_readings_count", 0) >= 3
            and (
                (_profile(f).normalized_goal == "lose" and f.get("weight_trend") == "gaining")
                or (_profile(f).normalized_goal == "gain" and f.get("weight_trend") == "losing")
            )
        ),
        action=_rule_weight_trend_mismatch_action,
        weight=45,
        cooldown_days=7,
    ),
    # Supporting Insight: Elevated Resting HR
    Rule(
        rule_id="vitals.elevated_resting_hr",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            f.get("resting_hr_baseline") is not None
            and _snapshot(f).resting_heart_rate is not None
            and _snapshot(f).resting_heart_rate > (f["resting_hr_baseline"] + 7.0)
        ),
        action=_rule_elevated_resting_hr_action,
        weight=40,
        cooldown_days=2,
    ),
]


def facts_short_sleep(f: dict[str, Any]) -> bool:
    consecutive = f.get("consecutive_short_sleep_days", 0)
    today_sleep = _snapshot(f).total_sleep_hours
    if today_sleep is not None and today_sleep < 6.0:
        consecutive += 1
    return consecutive >= 3


ALL_V1_RULES = [*SAFETY_RULES, *V1_RULES]

