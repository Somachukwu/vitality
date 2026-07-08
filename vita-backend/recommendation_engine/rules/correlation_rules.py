"""
Correlation rules — the "fusion" payoff. These are what make this an
integrated system rather than two separate trackers glued together.
They look at BOTH nutrition and vitals facts at once.
"""

from ..models import Priority, Recommendation
from ..rules_engine import Rule


def _snapshot(facts):
    return facts["snapshot"]


def _rule_high_carbs_low_sleep(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="correlation",
        priority=Priority.MEDIUM,
        title="High carbohydrate intake with short sleep",
        message=(
            "High carbohydrate intake combined with short sleep can affect blood "
            "sugar stability and next-day energy. Consider more protein/fiber at "
            "your next meal and prioritizing sleep tonight."
        ),
        evidence={"total_carbs_g": s.total_carbs_g, "total_sleep_hours": s.total_sleep_hours},
    )


def _rule_stress_and_surplus(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="correlation",
        priority=Priority.MEDIUM,
        title="Stress-linked eating pattern",
        message=(
            "Today combined an elevated stress score with a calorie surplus — a "
            "common stress-eating pattern. A short walk or breathing break before "
            "meals can help you eat more intentionally."
        ),
        evidence={"avg_stress_score": s.avg_stress_score, "calorie_balance": s.calorie_balance},
    )


def _rule_low_activity_high_calorie(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="correlation",
        priority=Priority.LOW,
        title="Calorie surplus with low activity",
        message=(
            "Today's calorie surplus wasn't offset by activity — steps were low. "
            "A brisk 20-30 minute walk would help balance today's intake."
        ),
        evidence={"total_steps": s.total_steps, "calorie_balance": s.calorie_balance},
    )


CORRELATION_RULES = [
    Rule(
        rule_id="correlation.high_carbs_low_sleep",
        category="correlation",
        condition=lambda f: (
            _snapshot(f).total_carbs_g > 250 and
            _snapshot(f).total_sleep_hours is not None and
            _snapshot(f).total_sleep_hours < 6.5
        ),
        action=_rule_high_carbs_low_sleep,
        weight=2,
    ),
    Rule(
        rule_id="correlation.stress_and_surplus",
        condition=lambda f: (
            _snapshot(f).avg_stress_score is not None and _snapshot(f).avg_stress_score > 60 and
            _snapshot(f).calorie_balance is not None and _snapshot(f).calorie_balance > 200
        ),
        category="correlation",
        action=_rule_stress_and_surplus,
        weight=2,
    ),
    Rule(
        rule_id="correlation.low_activity_high_calorie",
        category="correlation",
        condition=lambda f: (
            _snapshot(f).total_steps < 4000 and
            _snapshot(f).calorie_balance is not None and _snapshot(f).calorie_balance > 300
        ),
        action=_rule_low_activity_high_calorie,
        weight=1,
    ),
]
