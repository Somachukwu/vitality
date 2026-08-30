"""
Fallback and daily baseline wellness rules.
These fire with lower precedence (weight 25-35) when no critical or
anomaly-specific rules match, ensuring the user always receives
valuable daily guidance.
"""

from typing import Any

from ..models import Category, DailySnapshot, Priority, Recommendation, Tier, UserProfile
from ..rules_engine import Rule


def _snapshot(facts: dict[str, Any]) -> DailySnapshot:
    return facts["snapshot"]


def _profile(facts: dict[str, Any]) -> UserProfile:
    return facts["profile"]


def _rule_daily_wellness_focus_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    p = _profile(facts)
    goal_str = p.normalized_goal
    if goal_str == "lose":
        tip = "Focus on pairing dietary protein with fiber-rich vegetables to maintain satiety during your calorie deficit."
    elif goal_str == "gain":
        tip = "Ensure nutrient-dense calorie sources like nuts, whole grains, and lean proteins are distributed across your meals."
    else:
        tip = "Maintain steady energy levels by staying hydrated and spreading balanced whole-food meals evenly through your day."

    return Recommendation(
        category=Category.GOAL_PROGRESS.value,
        priority=Priority.LOW,
        tier=Tier.PRIMARY_ACTION,
        rule_id="lifestyle.daily_wellness_focus",
        title="Daily Wellness & Consistency",
        message=tip,
        evidence={"goal": goal_str, "target_calories": s.calorie_target},
        action_data={"action_label": "View Goals", "route": "/profile.html"},
        cooldown_days=1,
        confidence=0.8,
    )


def _rule_macro_balance_insight_action(facts: dict[str, Any]) -> Recommendation:
    s = _snapshot(facts)
    return Recommendation(
        category=Category.NUTRITION.value,
        priority=Priority.LOW,
        tier=Tier.SUPPORTING_INSIGHT,
        rule_id="lifestyle.macro_balance_insight",
        title="Balanced Energy Distribution",
        message=(
            f"Your logged intake today is {s.total_calories:.0f} kcal "
            f"({s.total_protein_g:.0f}g protein, {s.total_carbs_g:.0f}g carbs, {s.total_fat_g:.0f}g fat). "
            "Balancing all three macronutrients supports hormonal regulation and sustained physical energy."
        ),
        evidence={"calories": s.total_calories, "protein_g": s.total_protein_g, "carbs_g": s.total_carbs_g, "fat_g": s.total_fat_g},
        action_data={"action_label": "View Nutrition", "route": "/food-log.html"},
        cooldown_days=1,
        confidence=0.75,
    )


FALLBACK_RULES = [
    Rule(
        rule_id="lifestyle.daily_wellness_focus",
        category=Category.GOAL_PROGRESS.value,
        tier=Tier.PRIMARY_ACTION,
        condition=lambda f: True,
        action=_rule_daily_wellness_focus_action,
        weight=30,
        cooldown_days=1,
    ),
    Rule(
        rule_id="lifestyle.macro_balance_insight",
        category=Category.NUTRITION.value,
        tier=Tier.SUPPORTING_INSIGHT,
        condition=lambda f: True,
        action=_rule_macro_balance_insight_action,
        weight=25,
        cooldown_days=1,
    ),
]
