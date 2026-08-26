"""
A forward-chaining, explainable rule engine and arbiter.

Evaluates facts against registered rules, applies confidence-weighted scoring
and cooldown filters, and delivers a curated output:
  [Safety Alert (if active)] + [Top 1 Primary Action] + [Top 1 Supporting Insight]
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .models import Priority, Recommendation, Tier


@dataclass
class Rule:
    rule_id: str
    category: str
    tier: Tier = Tier.PRIMARY_ACTION
    condition: Callable[[dict[str, Any]], bool] = lambda f: False
    action: Callable[[dict[str, Any]], Recommendation] = lambda f: None  # type: ignore
    weight: int = 50
    cooldown_days: int = 1


class RuleEngine:
    def __init__(self):
        self._rules: list[Rule] = []

    def register(self, rule: Rule) -> None:
        self._rules.append(rule)

    def register_all(self, rules: list[Rule]) -> None:
        self._rules.extend(rules)

    def run(
        self,
        facts: dict[str, Any],
        active_cooldown_rules: set[str] | None = None,
        limit_delivery: bool = True,
    ) -> list[Recommendation]:
        """
        Executes forward chaining inference over facts.
        
        If limit_delivery is True (default for user UI), returns at most:
          - Any active Safety alert (Tier.SAFETY)
          - Top 1 Primary Action (Tier.PRIMARY_ACTION)
          - Top 1 Supporting Insight (Tier.SUPPORTING_INSIGHT)
        """
        cooldown_set = active_cooldown_rules or set()
        candidates: list[tuple[float, Recommendation]] = []

        for rule in self._rules:
            # Safety rules bypass cooldowns; standard rules respect cooldown
            if rule.tier != Tier.SAFETY and rule.rule_id in cooldown_set:
                continue

            try:
                if rule.condition(facts):
                    rec = rule.action(facts)
                    rec.rule_id = rule.rule_id
                    rec.tier = rule.tier
                    rec.cooldown_days = rule.cooldown_days
                    score = float(rule.weight) * float(rec.confidence)
                    candidates.append((score, rec))
            except Exception:
                # Missing or malformed data in one rule should never crash the engine
                continue

        # Sort all candidates by descending score
        candidates.sort(key=lambda item: item[0], reverse=True)

        if not limit_delivery:
            return [rec for _, rec in candidates]

        # Arbitration: Strict 1 Action + 1 Insight + Safety override
        safety_alerts: list[Recommendation] = []
        primary_action: Optional[Recommendation] = None
        supporting_insight: Optional[Recommendation] = None

        for _, rec in candidates:
            if rec.tier == Tier.SAFETY:
                safety_alerts.append(rec)
            elif rec.tier == Tier.PRIMARY_ACTION and primary_action is None:
                primary_action = rec
            elif rec.tier == Tier.SUPPORTING_INSIGHT and supporting_insight is None:
                supporting_insight = rec

        # Assemble final ordered output
        output: list[Recommendation] = []
        output.extend(safety_alerts)
        if primary_action:
            output.append(primary_action)
        if supporting_insight:
            output.append(supporting_insight)

        return output

