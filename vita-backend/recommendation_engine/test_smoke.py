import random
from datetime import date, datetime, timedelta

from recommendation_engine.fusion import build_daily_snapshot
from recommendation_engine.models import (
    ActivityLevel,
    FoodLogEntry,
    Sex,
    UserProfile,
    VitalsReading,
)
from recommendation_engine.recommendation_service import generate_recommendations, recommendations_to_dict

random.seed(0)

profile = UserProfile(
    user_id="u1",
    age=22,
    sex=Sex.MALE,
    height_cm=175,
    weight_kg=70,
    activity_level=ActivityLevel.MODERATE,
    goal="maintain",
)

# Build 15 days of synthetic history
history = []
base_day = date.today() - timedelta(days=15)
for i in range(15):
    d = base_day + timedelta(days=i)
    vitals = [
        VitalsReading(
            timestamp=datetime.combine(d, datetime.min.time()),
            heart_rate_bpm=random.uniform(60, 75),
            spo2_pct=random.uniform(96, 99),
            steps=random.randint(4000, 9000),
            stress_score=random.uniform(20, 45),
            sleep_minutes=random.uniform(390, 480),
        )
    ]
    food = [
        FoodLogEntry(
            timestamp=datetime.combine(d, datetime.min.time()),
            food_name="jollof rice and chicken",
            calories=random.uniform(1800, 2300),
            protein_g=random.uniform(60, 90),
            carbs_g=random.uniform(200, 280),
            fat_g=random.uniform(50, 80),
        )
    ]
    history.append(build_daily_snapshot(profile, d, vitals, food))

# Today: engineered to trigger several rules (low sleep, high stress, surplus, low SpO2)
today = date.today()
today_vitals = [
    VitalsReading(
        timestamp=datetime.combine(today, datetime.min.time()),
        heart_rate_bpm=88,
        spo2_pct=93.5,
        steps=1500,
        stress_score=78,
        sleep_minutes=280,
    )
]
today_food = [
    FoodLogEntry(
        timestamp=datetime.combine(today, datetime.min.time()),
        food_name="fried rice and suya",
        calories=3100,
        protein_g=70,
        carbs_g=340,
        fat_g=110,
    )
]

recs = generate_recommendations(
    profile=profile,
    day=today,
    vitals=today_vitals,
    food_logs=today_food,
    history=history,
)

print(f"{len(recs)} recommendations fired:\n")
for r in recommendations_to_dict(recs):
    print(f"[{r['priority'].upper()}] ({r['category']}) {r['title']}")
    print(f"  -> {r['message']}")
    print(f"  evidence: {r['evidence']}\n")
