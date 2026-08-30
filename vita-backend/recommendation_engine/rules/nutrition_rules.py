"""
Nutrition rules operating on DailySnapshot and UserProfile facts.
"""

from typing import Any

from ..models import Category, DailySnapshot, Priority, Recommendation, Tier, UserProfile
from ..rules_engine import Rule


def _snapshot(facts: dict[str, Any]) -> DailySnapshot:
    return facts["snapshot"]


def _profile(facts: dict[str, Any]) -> UserProfile:
    return facts["profile"]


def _rule_calorie_surplus_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="nutrition.calorie_surplus",
        title="Calorie Surplus Today",
        message=(
            f"You logged {s.total_calories:.0f} kcal against a target of {s.calorie_target:.0f} kcal "
            f"(+{s.calorie_balance:.0f} kcal over). A lighter dinner or an evening walk can help keep your weekly average aligned."
        ),
        evidence={"total_calories": s.total_calories, "calorie_target": s.calorie_target, "calorie_balance": s.calorie_balance},
        action_data={"action_label": "View Nutrition", "route": "/food-log.html"},
        cooldown_days=1,
        confidence=0.85,
    )


def _rule_calorie_deficit_moderate_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.MEDIUM,
        tier=Tier.PRIMARY_ACTION,
        rule_id="nutrition.calorie_deficit_moderate",
        title="Moderate Calorie Deficit",
        message=(
            f"You're currently {abs(s.calorie_balance or 0):.0f} kcal below your daily energy target. "
            "If you plan to exercise or recover from training, make sure your next meal includes quality complex carbs and protein."
        ),
        evidence={"total_calories": s.total_calories, "calorie_target": s.calorie_target, "calorie_balance": s.calorie_balance},
        action_data={"action_label": "Log Meal", "route": "/food-log.html"},
        cooldown_days=1,
        confidence=0.85,
    )


def _rule_protein_target_hit_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    p = _profile(facts)
    weight = p.weight_kg or 70.0
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.LOW,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="nutrition.protein_target_hit",
        title="Optimal Protein Intake",
        message=(
            f"Great job hitting {s.total_protein_g:.0f}g of protein today ({s.total_protein_g / weight:.1f}g/kg). "
            "Meeting your protein target supports cellular repair, muscle preservation, and steady energy."
        ),
        evidence={"total_protein_g": s.total_protein_g, "weight_kg": weight},
        action_data={"action_label": "View Macros", "route": "/food-log.html"},
        cooldown_days=2,
        confidence=0.9,
    )


NUTRITION_RULES = [
    Rule(
        rule_id="nutrition.calorie_surplus",
        category=Category.NUTRITION.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            _snapshot(f).meals_logged >= 2
            and _snapshot(f).calorie_balance is not None
            and _snapshot(f).calorie_balance > 350
        ),
        action=_rule_calorie_surplus_action,
        weight=62,
        cooldown_days=1,
    ),
    Rule(
        rule_id="nutrition.calorie_deficit_moderate",
        category=Category.NUTRITION.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: (
            _snapshot(f).meals_logged >= 2
            and _snapshot(f).calorie_balance is not None
            and -1000 <= _snapshot(f).calorie_balance < -500
        ),
        action=_rule_calorie_deficit_moderate_action,
        weight=60,
        cooldown_days=1,
    ),
    Rule(
        rule_id="nutrition.protein_target_hit",
        category=Category.NUTRITION.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: (
            _snapshot(f).meals_logged >= 2
            and _snapshot(f).total_protein_g >= (_profile(f).weight_kg or 70.0) * 1.2
        ),
        action=_rule_protein_target_hit_action,
        weight=52,
        cooldown_days=2,
    ),
]

