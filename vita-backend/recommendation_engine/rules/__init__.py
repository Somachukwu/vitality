from .correlation_rules import CORRELATION_RULES
from .fallback_rules import FALLBACK_RULES
from .nutrition_rules import NUTRITION_RULES
from .v1_rules import ALL_V1_RULES, SAFETY_RULES, V1_RULES
from .vitals_rules import VITALS_RULES

ALL_RULES = [
    *ALL_V1_RULES,
    *CORRELATION_RULES,
    *NUTRITION_RULES,
    *VITALS_RULES,
    *FALLBACK_RULES,
]

