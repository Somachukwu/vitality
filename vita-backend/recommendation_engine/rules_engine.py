"""
A deliberately simple, explainable rule engine.

Why not a full expert-system library (e.g. `experta`)? For a final-year
defense, you want to be able to open one file and explain exactly how a
recommendation was produced. This engine is ~40 lines and every rule is
just "condition function -> recommendation function".

Facts are just a dict. The ML layer (see ml/) adds extra keys to this
dict (e.g. "hr_anomaly": True) before the rules run, so ML output
influences which rules fire without the rules needing to know anything
about how ML works.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from .models import Recommendation


@dataclass
class Rule:
    rule_id: str
    category: str
    condition: Callable[[dict], bool]
    action: Callable[[dict], Recommendation]
    # Higher runs don't override lower — priority is just for output ordering
    weight: int = 1


class RuleEngine:
    def __init__(self):
        self._rules: list[Rule] = []

    def register(self, rule: Rule) -> None:
        self._rules.append(rule)

    def register_all(self, rules: list[Rule]) -> None:
        self._rules.extend(rules)

    def run(self, facts: dict) -> list[Recommendation]:
        fired: list[Recommendation] = []
        for rule in self._rules:
            try:
                if rule.condition(facts):
                    rec = rule.action(facts)
                    rec.rule_id = rule.rule_id
                    fired.append(rec)
            except (KeyError, TypeError):
                # Missing data for this rule's condition -> skip, don't crash
                # the whole recommendation run for one user's incomplete data.
                continue

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        fired.sort(key=lambda r: priority_order.get(r.priority.value, 9))
        return fired
