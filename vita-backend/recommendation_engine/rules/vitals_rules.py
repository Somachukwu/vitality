"""
Vitals and Activity rules operating on DailySnapshot facts.
"""

from typing import Any

from ..models import Category, DailySnapshot, Priority, Recommendation, Tier
from ..rules_engine import Rule


def _snapshot(facts: dict[str, Any]) -> DailySnapshot:
    return facts["snapshot"]


def _rule_daily_short_sleep_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="vitals.daily_short_sleep",
        title="Short Sleep Duration",
        message=(
            f"You logged {s.total_sleep_hours:.1f} hours of sleep last night. "
            "Short sleep can diminish cognitive focus and increase appetite. Aim for a calming wind-down routine tonight."
        ),
        evidence={"total_sleep_hours": s.total_sleep_hours},
        action_data={"action_label": "View Sleep", "route": "vitals.html"},
        cooldown_days=2,
        confidence=0.9,
    )


def _rule_mild_low_spo2_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    val = s.avg_spo2 or s.min_spo2 or 93.0
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.MEDIUM,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="vitals.mild_low_spo2",
        title="Slightly Low Blood Oxygen",
        message=(
            f"Overnight blood oxygen averaged {val:.1f}% (normal baseline is 95-100%). "
            "Occasional mild dips can occur with sleeping posture or nasal congestion, but monitor for sustained trends."
        ),
        evidence={"avg_spo2": val},
        action_data={"action_label": "View Vitals", "route": "vitals.html"},
        cooldown_days=2,
        confidence=0.85,
    )


def _rule_high_stress_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.HEALTH_ALERT.value,
        priority=Priority.LOW,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="vitals.high_stress",
        title="Elevated Stress Score",
        message=(
            f"Your daytime stress score averaged {s.avg_stress_score:.0f}/100 today. "
            "A 5-minute deep breathing session or a short break from screens can help activate your parasympathetic nervous system."
        ),
        evidence={"avg_stress_score": s.avg_stress_score},
        action_data={"action_label": "View Vitals", "route": "vitals.html"},
        cooldown_days=2,
        confidence=0.85,
    )


def _rule_daily_low_steps_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.ACTIVITY.value,
        priority=Priority.LOW,
        tier=Tier.PRIMARY_ACTION,
        rule_id="activity.daily_low_steps",
        title="Increase Daily Movement",
        message=(
            f"You have logged {s.total_steps:,} steps today. "
            "Taking a brief walk or opting for stairs over elevators will help keep you on track for active recovery."
        ),
        evidence={"total_steps": s.total_steps},
        action_data={"action_label": "Track Activity", "route": "vitals.html"},
        cooldown_days=2,
        confidence=0.85,
    )


def _rule_step_milestone_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.ACTIVITY.value,
        priority=Priority.LOW,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="activity.step_milestone",
        title="Daily Step Milestone Achieved",
        message=(
            f"Excellent movement! You've logged {s.total_steps:,} steps today. "
            "Consistent daily activity significantly supports cardiovascular health and metabolic rate."
        ),
        evidence={"total_steps": s.total_steps},
        action_data={"action_label": "View Activity", "route": "vitals.html"},
        cooldown_days=2,
        confidence=0.9,
    )



VITALS_RULES = [
    Rule(
        rule_id="vitals.daily_short_sleep",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            _snapshot(f).total_sleep_hours is not None
            and 0 < _snapshot(f).total_sleep_hours < 6.0
        ),
        action=_rule_daily_short_sleep_action,
        weight=70,
        cooldown_days=2,
    ),
    Rule(
        rule_id="vitals.mild_low_spo2",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            _snapshot(f).avg_spo2 is not None
            and 90.0 <= _snapshot(f).avg_spo2 < 95.0
        ),
        action=_rule_mild_low_spo2_action,
        weight=55,
        cooldown_days=2,
    ),
    Rule(
        rule_id="vitals.high_stress",
        category=Category.HEALTH_ALERT.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            _snapshot(f).avg_stress_score is not None
            and _snapshot(f).avg_stress_score > 65
        ),
        action=_rule_high_stress_action,
        weight=50,
        cooldown_days=2,
    ),
    Rule(
        rule_id="activity.daily_low_steps",
        category=Category.ACTIVITY.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            0 < _snapshot(f).total_steps < 3500
        ),
        action=_rule_daily_low_steps_action,
        weight=58,
        cooldown_days=2,
    ),
    Rule(
        rule_id="activity.step_milestone",
        category=Category.ACTIVITY.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            _snapshot(f).total_steps >= 10000
        ),
        action=_rule_step_milestone_action,
        weight=54,
        cooldown_days=2,
    ),
]

