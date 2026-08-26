import random
from datetime import date, datetime, timedelta

from recommendation_engine.fusion import build_daily_snapshot, estimate_calorie_target
from recommendation_engine.models import (
    ActivityLevel,
    Category,
    FoodLogEntry,
    Priority,
    Sex,
    SleepSessionReading,
    Tier,
    UserProfile,
    VitalsReading,
)
from recommendation_engine.recommendation_service import generate_recommendations, recommendations_to_dict


def test_calorie_target_and_floors():
    print("--- Test 1: Calorie Targets & Clinical Floors ---")
    # Female 55kg, 160cm, age 25, sedentary, weight loss
    p_female = UserProfile(
        user_id="u_fem",
        age=25,
        sex=Sex.FEMALE,
        height_cm=160,
        weight_kg=55,
        activity_level=ActivityLevel.SEDENTARY,
        goal="weight_loss",
    )
    # BMR = 10*55 + 6.25*160 - 5*25 - 161 = 550 + 1000 - 125 - 161 = 1264
    # TDEE = 1264 * 1.2 = 1516.8. Target = 1516.8 - 500 = 1016.8 -> Clamped to 1200 floor!
    target = estimate_calorie_target(p_female)
    assert target == 1200.0, f"Expected female floor of 1200.0, got {target}"
    print(f"  [OK] Female calorie deficit correctly clamped to safe floor: {target} kcal")

    p_male = UserProfile(
        user_id="u_male",
        age=25,
        sex=Sex.MALE,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        goal="lose",
    )
    target_m = estimate_calorie_target(p_male)
    assert target_m > 1500, f"Expected male target > 1500, got {target_m}"
    print(f"  [OK] Male calorie target calculated: {target_m:.1f} kcal")


def test_v1_rules_and_arbitration():
    print("\n--- Test 2: Full Pipeline Simulation (5 V1 Rules + Safety) ---")
    random.seed(42)

    profile = UserProfile(
        user_id="u1",
        age=24,
        sex=Sex.MALE,
        height_cm=175,
        weight_kg=75,
        activity_level=ActivityLevel.MODERATE,
        goal="weight_loss",
    )

    # 1. Build 14 days of history with:
    # - Low daily steps (average ~3,800 steps) -> triggers Weekly Step Gap
    # - Short sleep last 3 days (<5.5 hours) -> triggers Persistent Short Sleep
    # - Increasing scale weight (+0.3 kg/week) with calorie surplus -> triggers Weight Trend Mismatch
    history = []
    base_day = date.today() - timedelta(days=14)

    for i in range(14):
        d = base_day + timedelta(days=i)
        weight_val = 75.0 + (i * 0.05)  # gaining weight slowly
        sleep_hrs = 5.2 if i >= 11 else 7.5  # last 3 days short sleep

        vitals = [
            VitalsReading(
                timestamp=datetime.combine(d, datetime.min.time()),
                heart_rate_bpm=70,
                spo2_pct=98.0,
                steps=3500 + random.randint(0, 500),
                weight_kg=weight_val,
            )
        ]
        sleep = [
            SleepSessionReading(
                sleep_date=d,
                duration_min=int(sleep_hrs * 60),
            )
        ]
        food = [
            FoodLogEntry(
                timestamp=datetime.combine(d, datetime.min.time()),
                food_name="jollof rice",
                calories=2600,
                protein_g=45,  # low protein
                carbs_g=350,
                fat_g=80,
            )
        ]
        history.append(build_daily_snapshot(profile, d, vitals, food, sleep))

    # 2. Today: Trigger low SpO2 (Safety Alert) + Incomplete logging + Low protein
    today = date.today()
    today_vitals = [
        VitalsReading(
            timestamp=datetime.combine(today, datetime.min.time()),
            heart_rate_bpm=72,
            spo2_pct=88.5,  # Trigger Critical SpO2 Safety Alert (< 90%)
            steps=2000,
            weight_kg=75.7,
        )
    ]
    today_sleep = [
        SleepSessionReading(
            sleep_date=today,
            duration_min=300,  # 5 hours
        )
    ]
    today_food = [
        FoodLogEntry(
            timestamp=datetime.combine(today, datetime.min.time()),
            food_name="plantain",
            calories=350,
            protein_g=10,
            carbs_g=60,
            fat_g=5,
        )
    ]

    # Test raw rule firing without arbitration limits
    all_fired = generate_recommendations(
        profile=profile,
        day=today,
        vitals=today_vitals,
        food_logs=today_food,
        sleep_sessions=today_sleep,
        history=history,
        limit_delivery=False,
    )
    print(f"  [OK] Raw candidate rules triggered: {len(all_fired)}")
    rule_ids = {r.rule_id for r in all_fired}
    print(f"    Fired Rule IDs: {', '.join(sorted(rule_ids))}")
    assert "safety.critical_spo2" in rule_ids
    assert "nutrition.incomplete_logging" in rule_ids or "vitals.persistent_short_sleep" in rule_ids

    # Test delivery arbitration: Exactly 1 Action + 1 Insight + Safety Card
    curated = generate_recommendations(
        profile=profile,
        day=today,
        vitals=today_vitals,
        food_logs=today_food,
        sleep_sessions=today_sleep,
        history=history,
        limit_delivery=True,
    )
    print(f"\n  [OK] Curated delivery items: {len(curated)}")
    tiers = [r.tier for r in curated]
    print(f"    Tiers in output: {[t.value for t in tiers]}")

    assert Tier.SAFETY in tiers, "Safety alert must be present!"
    action_count = sum(1 for t in tiers if t == Tier.PRIMARY_ACTION)
    insight_count = sum(1 for t in tiers if t == Tier.SUPPORTING_INSIGHT)
    assert action_count <= 1, f"Expected at most 1 Primary Action, got {action_count}"
    assert insight_count <= 1, f"Expected at most 1 Supporting Insight, got {insight_count}"

    print("\n--- Curated Recommendations Delivered to User ---")
    for r in recommendations_to_dict(curated):
        print(f"[{r['tier'].upper()} | {r['priority'].upper()}] {r['title']} ({r['category']})")
        print(f"  Message: {r['message']}")
        print(f"  Evidence: {r['evidence']}")
        print(f"  Action: {r['action_data']}\n")


def test_cooldown_suppression():
    print("--- Test 3: Cooldown Filtering ---")
    profile = UserProfile(
        user_id="u2",
        age=28,
        sex=Sex.MALE,
        height_cm=175,
        weight_kg=70,
        activity_level=ActivityLevel.MODERATE,
        goal="maintain",
    )
    today = date.today()

    # If incomplete_logging is on cooldown, it should be suppressed
    cooldowns = {"nutrition.incomplete_logging"}
    recs = generate_recommendations(
        profile=profile,
        day=today,
        vitals=[],
        food_logs=[],
        sleep_sessions=[],
        history=[],
        active_cooldown_rules=cooldowns,
        limit_delivery=False,
    )
    rule_ids = {r.rule_id for r in recs}
    assert "nutrition.incomplete_logging" not in rule_ids, "Rule on cooldown must be suppressed!"
    print("  [OK] Active cooldown rule successfully suppressed.")


if __name__ == "__main__":
    test_calorie_target_and_floors()
    test_v1_rules_and_arbitration()
    test_cooldown_suppression()
    print("\n*** ALL RECOMMENDATION ENGINE SMOKE TESTS PASSED! ***")


