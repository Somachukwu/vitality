"""
Vitals rules — note that skin temperature is deviation-from-baseline
(Fitbit limitation), never treated as an absolute clinical reading.
"""

from ..models import Priority, Recommendation
from ..rules_engine import Rule


def _snapshot(facts):
    return facts["snapshot"]


def _rule_low_spo2(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="vitals",
        priority=Priority.HIGH,
        title="Lower than usual blood oxygen",
        message=(
            f"Average overnight SpO2 was {s.avg_spo2:.1f}%, below the healthy "
            "resting range (95-100%). This isn't a diagnosis — if this persists "
            "over several nights, please consult a doctor."
        ),
        evidence={"avg_spo2": s.avg_spo2},
    )


def _rule_elevated_resting_hr(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="vitals",
        priority=Priority.MEDIUM,
        title="Elevated resting heart rate",
        message=(
            f"Resting heart rate today (~{s.resting_heart_rate:.0f} bpm) is above your "
            "recent baseline. This can reflect poor sleep, stress, dehydration, or "
            "incomplete recovery — an easier day of training may help."
        ),
        evidence={"resting_heart_rate": s.resting_heart_rate},
    )


def _rule_low_sleep(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="vitals",
        priority=Priority.MEDIUM,
        title="Short sleep duration",
        message=(
            f"You slept about {s.total_sleep_hours:.1f} hours. Adults generally need "
            "7-9 hours — short sleep tends to compound with stress and eating patterns "
            "over the following days."
        ),
        evidence={"total_sleep_hours": s.total_sleep_hours},
    )


def _rule_high_stress(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="vitals",
        priority=Priority.MEDIUM,
        title="Elevated stress score",
        message=(
            f"Your all-day stress score averaged {s.avg_stress_score:.0f}/100 today, "
            "higher than typical. Consider a short break, walk, or breathing exercise."
        ),
        evidence={"avg_stress_score": s.avg_stress_score},
    )


def _rule_low_steps(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="vitals",
        priority=Priority.LOW,
        title="Low activity today",
        message=f"Only {s.total_steps} steps logged today — a short walk would help hit a healthier daily baseline.",
        evidence={"total_steps": s.total_steps},
    )


VITALS_RULES = [
    Rule(
        rule_id="vitals.low_spo2",
        category="vitals",
        condition=lambda f: _snapshot(f).avg_spo2 is not None and _snapshot(f).avg_spo2 < 95,
        action=_rule_low_spo2,
        weight=4,
    ),
    Rule(
        rule_id="vitals.elevated_resting_hr",
        category="vitals",
        condition=lambda f: (
            f.get("resting_hr_baseline") is not None
            and _snapshot(f).resting_heart_rate is not None
            and _snapshot(f).resting_heart_rate > f["resting_hr_baseline"] + 8
        ),
        action=_rule_elevated_resting_hr,
        weight=2,
    ),
    Rule(
        rule_id="vitals.low_sleep",
        category="vitals",
        condition=lambda f: _snapshot(f).total_sleep_hours is not None and _snapshot(f).total_sleep_hours < 6,
        action=_rule_low_sleep,
        weight=2,
    ),
    Rule(
        rule_id="vitals.high_stress",
        category="vitals",
        condition=lambda f: _snapshot(f).avg_stress_score is not None and _snapshot(f).avg_stress_score > 65,
        action=_rule_high_stress,
        weight=2,
    ),
    Rule(
        rule_id="vitals.low_steps",
        category="vitals",
        condition=lambda f: _snapshot(f).total_steps < 3000,
        action=_rule_low_steps,
        weight=1,
    ),
]
