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
    serving_description: str


# TODO: verify against the Nigerian Food Composition Table (NFCT) and cite it in your report.
NUTRITION_TABLE: dict[str, NutritionInfo] = {
    "akarabread": NutritionInfo(350, 12, 40, 15, "2 akara balls + 2 slices bread"),
    "banga": NutritionInfo(450, 18, 8, 35, "1 bowl (~250g), soup only, no starch"),
    "bitterleaf": NutritionInfo(380, 20, 8, 28, "1 bowl (~250g) with meat/fish"),
    "edikakong": NutritionInfo(420, 24, 8, 30, "1 bowl (~300g) with meat/fish"),
    "egusi": NutritionInfo(520, 22, 12, 40, "1 bowl (~250g) with meat/fish"),
    "ewedu": NutritionInfo(150, 6, 10, 9, "1 bowl (~200g), soup only"),
    "garriandgrounut": NutritionInfo(380, 8, 65, 12, "1 serving (~150g garri + 30g groundnuts)"),
    "jellof": NutritionInfo(450, 8, 75, 12, "1 plate (~300g)"),
    "moimoi": NutritionInfo(210, 14, 18, 9, "1 wrap (~150g)"),
    "nkwobi": NutritionInfo(480, 26, 6, 38, "1 serving (~200g)"),
    "ofeowerri": NutritionInfo(430, 24, 8, 32, "1 bowl (~300g) with meat/fish"),
    "ogbono": NutritionInfo(480, 20, 10, 38, "1 bowl (~250g) with meat/fish"),
    "okra": NutritionInfo(380, 20, 10, 26, "1 bowl (~250g) with meat/fish"),
    "pufpuf": NutritionInfo(300, 5, 40, 14, "4-5 pieces (~100g)"),
}


def get_nutrition(food_class: str) -> NutritionInfo:
    if food_class not in NUTRITION_TABLE:
        raise KeyError(
            f"No nutrition entry for '{food_class}'. Add it to NUTRITION_TABLE in nutrition_lookup.py."
        )
    return NUTRITION_TABLE[food_class]
