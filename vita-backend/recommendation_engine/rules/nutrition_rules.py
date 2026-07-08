"""
Nutrition rules operate on facts["snapshot"] (a DailySnapshot).
"""

from ..models import Priority, Recommendation
from ..rules_engine import Rule


def _snapshot(facts):
    return facts["snapshot"]


def _rule_calorie_surplus(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="nutrition",
        priority=Priority.MEDIUM,
        title="Calorie surplus today",
        message=(
            f"You logged {s.total_calories:.0f} kcal against a target of "
            f"{s.calorie_target:.0f} kcal — about {s.calorie_balance:.0f} kcal over. "
            "Consider a lighter dinner or a short walk to help balance it out."
        ),
        evidence={"total_calories": s.total_calories, "calorie_target": s.calorie_target},
    )


def _rule_calorie_deficit_large(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="nutrition",
        priority=Priority.HIGH,
        title="Significant calorie deficit",
        message=(
            f"You're about {abs(s.calorie_balance):.0f} kcal under your target today. "
            "Occasional deficits are fine, but a pattern of large deficits can affect "
            "energy and recovery — make sure your next meal covers the gap."
        ),
        evidence={"calorie_balance": s.calorie_balance},
    )


def _rule_low_protein(facts) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category="nutrition",
        priority=Priority.LOW,
        title="Protein intake below target",
        message=(
            f"Protein intake today was {s.total_protein_g:.0f}g. For your weight "
            f"({facts['profile'].weight_kg:.0f}kg), aiming for roughly "
            f"{facts['profile'].weight_kg * 1.2:.0f}-{facts['profile'].weight_kg * 1.6:.0f}g "
            "supports recovery and satiety."
        ),
        evidence={"total_protein_g": s.total_protein_g},
    )


def _rule_no_meals_logged(facts) -> Recommendation:
    return Recommendation(
        category="nutrition",
        priority=Priority.LOW,
        title="No meals logged today",
        message="No meals were logged today — log at least one meal so recommendations stay accurate.",
        evidence={"meals_logged": 0},
    )


NUTRITION_RULES = [
    Rule(
        rule_id="nutrition.calorie_surplus",
        category="nutrition",
        condition=lambda f: _snapshot(f).calorie_balance is not None and _snapshot(f).calorie_balance > 300,
        action=_rule_calorie_surplus,
        weight=2,
    ),
    Rule(
        rule_id="nutrition.calorie_deficit_large",
        category="nutrition",
        condition=lambda f: _snapshot(f).calorie_balance is not None and _snapshot(f).calorie_balance < -500,
        action=_rule_calorie_deficit_large,
        weight=3,
    ),
    Rule(
        rule_id="nutrition.low_protein",
        category="nutrition",
        condition=lambda f: (
            _snapshot(f).total_protein_g > 0
            and _snapshot(f).total_protein_g < f["profile"].weight_kg * 1.0
        ),
        action=_rule_low_protein,
        weight=1,
    ),
    Rule(
        rule_id="nutrition.no_meals_logged",
        category="nutrition",
        condition=lambda f: _snapshot(f).meals_logged == 0,
        action=_rule_no_meals_logged,
        weight=1,
    ),
]
