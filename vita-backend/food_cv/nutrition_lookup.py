"""
Maps a recognized food class -> estimated calories/macros for one typical
serving.

IMPORTANT SCOPE NOTE (document this in your report, same way the Fitbit
temperature deviation was documented as a scope limitation): this system
estimates portion size as "one typical serving" per dish, not true
volumetric portion estimation from the image (which would need depth
estimation or a reference object in-frame — out of scope for this
project). The user can adjust a portion multiplier in the UI if their
plate is bigger/smaller than typical. This is a reasonable, defensible
simplification consistent with published Nigerian food recognition
systems, which similarly use average calorie values per class rather
than per-pixel portion estimation.

Values below are rough averages for common Nigerian dishes, per typical
serving — VERIFY these against a Nigerian food composition table (e.g.
NFCT - Nigerian Food Composition Table) before relying on them for your
report or defense. Treat these as placeholders to replace with sourced
figures.
"""

from dataclasses import dataclass


@dataclass
class NutritionInfo:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None
    serving_description: str


NUTRITION_TABLE: dict[str, NutritionInfo] = {
    "abacha": NutritionInfo(430.4, 14.30, 62.70, 13.60, 6.70, "per 100 g"),
    "fried rice": NutritionInfo(172.88, 2.56, 32.55, 3.36, 1.10, "per 100 g"),
    "akara": NutritionInfo(218.0, 12.07, 23.76, 8.30, 0.87, "per 100 g"),
    "banga": NutritionInfo(131.7, 13.61, 1.36, 7.98, 0.38, "per 100 g"),
    "bitterleaf": NutritionInfo(179.0, 9.40, 14.20, 9.40, 4.70, "per 100 g"),
    "egusi": NutritionInfo(179.5, 8.59, 1.95, 15.26, 0.79, "per 100 g"),
    "ewedu": NutritionInfo(37.0, 2.00, 5.00, 1.00, 1.00, "per 100 g"),
    "beans": NutritionInfo(147.56, 11.605, 21.52, 0.496, 5.30, "per 100 g"),
    "jellof": NutritionInfo(144.545, 2.635, 27.505, 2.665, None, "per 100 g"),
    "moimoi": NutritionInfo(108.406, 6.47, 15.74, 2.174, None, "per 100 g"),
    "ofeowerri": NutritionInfo(438.0, 28.00, 14.00, 30.00, 6.00, "per 100 g"),
    "ogbono": NutritionInfo(227.0, 11.14, 0.74, 19.94, 0.93, "per 100 g"),
    "okra": NutritionInfo(172.3, 11.17, 4.44, 12.21, 1.87, "per 100 g"),
    "pufpuf": NutritionInfo(242.0, 5.00, 51.00, 2.00, 2.00, "per 100 g"),
    "spaghetti": NutritionInfo(123.5, 4.20, 26.00, 0.30, None, "per 100 g"),
}

# Alias map to handle model class names, underscores, and common variations
ALIASES: dict[str, str] = {
    "akarabread": "akara",
    "akara bread": "akara",
    "fried_rice": "fried rice",
    "friedrice": "fried rice",
    "jollof": "jellof",
    "jollof_rice": "jellof",
    "jollofrice": "jellof",
    "jellof_rice": "jellof",
    "jellof rice": "jellof",
    "moi_moi": "moimoi",
    "moi moi": "moimoi",
    "moyi moyi": "moimoi",
    "moyimoyi": "moimoi",
    "puff_puff": "pufpuf",
    "puff puff": "pufpuf",
    "puffpuff": "pufpuf",
    "ofe_owerri": "ofeowerri",
    "ofe owerri": "ofeowerri",
    "banga_soup": "banga",
    "banga soup": "banga",
    "bitterleaf_soup": "bitterleaf",
    "bitterleaf soup": "bitterleaf",
    "egusi_soup": "egusi",
    "egusi soup": "egusi",
    "ogbono_soup": "ogbono",
    "ogbono soup": "ogbono",
    "okra_soup": "okra",
    "okra soup": "okra",
    "okro": "okra",
    "okro soup": "okra",
    "ewedu_soup": "ewedu",
    "ewedu soup": "ewedu",
    "beans porridge": "beans",
    "beans_porridge": "beans",
}


def get_nutrition(food_class: str) -> NutritionInfo:
    key = food_class.strip().lower()
    # Check direct match
    if key in NUTRITION_TABLE:
        return NUTRITION_TABLE[key]

    # Check alias map
    if key in ALIASES and ALIASES[key] in NUTRITION_TABLE:
        return NUTRITION_TABLE[ALIASES[key]]

    # Try matching without underscores or extra spaces
    normalized_key = key.replace("_", " ").strip()
    if normalized_key in NUTRITION_TABLE:
        return NUTRITION_TABLE[normalized_key]
    if normalized_key in ALIASES and ALIASES[normalized_key] in NUTRITION_TABLE:
        return NUTRITION_TABLE[ALIASES[normalized_key]]

    no_space_key = key.replace("_", "").replace(" ", "").strip()
    if no_space_key in NUTRITION_TABLE:
        return NUTRITION_TABLE[no_space_key]
    if no_space_key in ALIASES and ALIASES[no_space_key] in NUTRITION_TABLE:
        return NUTRITION_TABLE[ALIASES[no_space_key]]

    raise KeyError(
        f"No nutrition entry for '{food_class}'. Available items: {', '.join(sorted(NUTRITION_TABLE.keys()))}"
    )
