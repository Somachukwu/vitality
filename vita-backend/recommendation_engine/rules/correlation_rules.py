"""
Correlation rules — the "fusion" payoff. These look at BOTH nutrition
and vitals facts simultaneously.
"""

from typing import Any

from ..models import Category, DailySnapshot, Priority, Recommendation, Tier
from ..rules_engine import Rule


def _snapshot(facts: dict[str, Any]) -> DailySnapshot:
    return facts["snapshot"]


def _rule_high_carbs_low_sleep_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="correlation.high_carbs_low_sleep",
        title="High Carbs with Short Sleep",
        message=(
            f"Logged carbs ({s.total_carbs_g:.0f}g) combined with short sleep ({s.total_sleep_hours:.1f}h) "
            "can amplify blood sugar swings and afternoon fatigue. Prioritize protein and fiber for your next meal."
        ),
        evidence={"total_carbs_g": s.total_carbs_g, "total_sleep_hours": s.total_sleep_hours},
        action_data={"action_label": "View Food Log", "route": "/food-log.html"},
        cooldown_days=2,
        confidence=0.9,
    )


def _rule_stress_and_surplus_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.MEDIUM,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="correlation.stress_and_surplus",
        title="Stress-Linked Energy Intake",
        message=(
            f"Today combined an elevated stress reading ({s.avg_stress_score:.0f}/100) with a calorie surplus "
            f"(+{s.calorie_balance:.0f} kcal). Taking a short walk or breathing pause before eating helps regulate appetite."
        ),
        evidence={"avg_stress_score": s.avg_stress_score, "calorie_balance": s.calorie_balance},
        action_data={"action_label": "View Vitals", "route": "/vitals.html"},
        cooldown_days=2,
        confidence=0.85,
    )


def _rule_low_activity_high_calorie_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.ACTIVITY.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="correlation.low_activity_high_calorie",
        title="Calorie Surplus with Low Activity",
        message=(
            f"Logged intake is running +{s.calorie_balance:.0f} kcal over target while daily steps are low ({s.total_steps:,} steps). "
            "A brisk 20-30 minute walk this evening will help rebalance energy expenditure."
        ),
        evidence={"total_steps": s.total_steps, "calorie_balance": s.calorie_balance},
        action_data={"action_label": "Track Activity", "route": "/vitals.html"},
        cooldown_days=2,
        confidence=0.85,
    )


CORRELATION_RULES = [
    Rule(
        rule_id="correlation.high_carbs_low_sleep",
        category=Category.NUTRITION.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            _snapshot(f).total_carbs_g > 220
            and _snapshot(f).total_sleep_hours is not None
            and _snapshot(f).total_sleep_hours < 6.5
        ),
        action=_rule_high_carbs_low_sleep_action,
        weight=72,
        cooldown_days=2,
    ),
    Rule(
        rule_id="correlation.stress_and_surplus",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            _snapshot(f).avg_stress_score is not None
            and _snapshot(f).avg_stress_score > 60
            and _snapshot(f).calorie_balance is not None
            and _snapshot(f).calorie_balance > 200
        ),
        action=_rule_stress_and_surplus_action,
        weight=68,
        cooldown_days=2,
    ),
    Rule(
        rule_id="correlation.low_activity_high_calorie",
        category=Category.ACTIVITY.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            _snapshot(f).total_steps < 4500
            and _snapshot(f).calorie_balance is not None
            and _snapshot(f).calorie_balance > 250
        ),
        action=_rule_low_activity_high_calorie_action,
        weight=64,
        cooldown_days=2,
    ),
]

