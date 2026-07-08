# Vitality Recommendation Engine

A hybrid rule-based expert system with an ML pattern-detection layer,
designed for a Fitbit-Sense-2-fed, computer-vision-food-logging health
platform.

## Why this design (for your report / defense)

The project title calls this an **"Expert Recommendation System"** —
so the final decision logic is a transparent, forward-chaining **rule
engine**, not a black-box model. Every recommendation can be traced
back to the exact rule and the exact data (`evidence` field) that
triggered it. That's easy to defend in a viva and easy to demo.

ML is used *underneath* the rules, not instead of them:
- **Isolation Forest** (`ml/anomaly_detection.py`) flags days that look
  statistically unusual for that specific user, based on their own
  recent history (no external dataset needed).
- **Trend detection** (`ml/trend_detection.py`) uses OLS slope over a
  rolling window to detect rising/falling patterns in resting HR,
  sleep, and stress.

Both add facts (e.g. `"resting_hr_trend": "rising"`) to a shared facts
dict. The rule engine reacts to those facts the same way it reacts to
raw data — so your report can honestly describe this as "hybrid",
while the actual explanation given to users stays rule-based and
readable.

## Architecture

```
Fitbit vitals + CV food logs
        │
        ▼
   fusion.py  ──────► DailySnapshot (today)
        │
        ▼
  ml/trend_detection.py  ─┐
  ml/anomaly_detection.py ─┼──► extra facts (trend/anomaly flags)
        │                 │
        ▼                 ▼
          facts = {snapshot, profile, ...ml facts}
                        │
                        ▼
              rules_engine.py (RuleEngine)
           ├─ rules/nutrition_rules.py
           ├─ rules/vitals_rules.py
           └─ rules/correlation_rules.py
                        │
                        ▼
              list[Recommendation]
```

## Files

- `models.py` — all data shapes (UserProfile, VitalsReading, FoodLogEntry, DailySnapshot, Recommendation)
- `fusion.py` — combines raw vitals + food logs into one DailySnapshot; BMR/TDEE calorie target calc (Mifflin-St Jeor)
- `rules_engine.py` — the ~40-line rule engine core
- `rules/` — the actual rule definitions, split by category
- `ml/` — anomaly + trend detection, both optional/graceful with sparse data
- `recommendation_service.py` — the single function your backend calls: `generate_recommendations(...)`
- `api_example.py` — example FastAPI route showing integration (adapt to your own DB functions)
- `test_smoke.py` — runnable example with synthetic data

## How to integrate into your existing backend

```python
from recommendation_engine import generate_recommendations, recommendations_to_dict

recs = generate_recommendations(
    profile=user_profile,          # build from your users table
    day=today,
    vitals=todays_vitals,          # build from Fitbit API pull
    food_logs=todays_food_logs,    # build from your CV module's output
    history=last_30_days,          # your cached DailySnapshots, oldest→newest
)
return recommendations_to_dict(recs)
```

You'll want a small job (cron, or triggered on Fitbit webhook sync) that:
1. Pulls the day's Fitbit intraday data
2. Builds a `DailySnapshot` via `fusion.build_daily_snapshot(...)` once the day is "closed" (e.g. end of day or next morning)
3. Stores that snapshot — this becomes tomorrow's `history`

## Extending the rules

Add a new `Rule(...)` to the relevant file in `rules/`, then it's
automatically picked up via `rules/__init__.py`'s `ALL_RULES`. A rule
is just:

```python
Rule(
    rule_id="nutrition.some_new_rule",
    category="nutrition",
    condition=lambda f: f["snapshot"].total_calories > 3500,
    action=lambda f: Recommendation(...),
    weight=1,
)
```

## Known scope notes (for your report)

- Fitbit skin temperature is deviation-from-baseline, not an absolute
  reading — nothing here treats it as a clinical thermometer value.
- Ambient humidity was dropped from scope (no wearable measures it).
- Anomaly/trend detection require a minimum history (10 and 5 days
  respectively) before activating — before that, the rule engine still
  works fully on rule-only logic.

## Run the smoke test

```bash
pip install -r requirements.txt
python3 -m recommendation_engine.test_smoke
```
