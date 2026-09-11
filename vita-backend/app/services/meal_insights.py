from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.models.meal import Meal
from app.models.recommendation import Recommendation
from app.models.user import User


def update_meal_insights_after_change(
    user_id: int,
    db: Session,
    background_tasks: Optional[BackgroundTasks] = None,
):
    """
    Called whenever meals are added, edited, or deleted (via /food/log, /meals/, etc.).
    Keeps the meal progress insight, midday meal check, and onboarding retirement
    in sync so the dashboard spotlight and insights page reflect the user's latest meal immediately.
    """
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = datetime.combine(now_naive.date(), datetime.min.time())

    # 1. Fetch user and today's meals
    user = db.get(User, user_id)
    if not user:
        return

    today_meals = (
        db.query(Meal)
        .filter(Meal.user_id == user_id, Meal.logged_at >= today_start)
        .order_by(Meal.logged_at.asc())
        .all()
    )
    meals_count = len(today_meals)

    # 2. Retire first-time user onboarding insight permanently
    db.query(Recommendation).filter(
        Recommendation.user_id == user_id,
        Recommendation.rule_id == "lifestyle.set_daily_targets",
        Recommendation.is_read == False,
    ).update({"is_read": True}, synchronize_session=False)

    if meals_count > 0:
        # 3. Mark any existing midday meal prompt as read (preserves history for insights page)
        db.query(Recommendation).filter(
            Recommendation.user_id == user_id,
            Recommendation.rule_id == "time.midday_meal_prompt",
            Recommendation.created_at >= today_start,
            Recommendation.is_read == False,
        ).update({"is_read": True}, synchronize_session=False)

        # 4. Compute totals and build meal milestone insight
        total_cals = round(sum(m.total_calories for m in today_meals))
        target_cals = round(user.daily_calorie_target or 2200)
        first_name = user.name.split()[0] if user.name else "there"

        calorie_met = target_cals > 0 and total_cals >= target_cals
        if calorie_met:
            meal_rule_id = "milestone.calories_met"
            meal_title = "Calorie Target Crushed! 🎉"
            meal_msg = (
                f"You did it, {first_name}! You've reached your daily calorie target "
                f"({total_cals:,} / {target_cals:,} kcal). Keep fuelling your body well — "
                f"great nutrition is the foundation of great health!"
            )
        else:
            meal_rule_id = "milestone.meals_logged_on_track"
            meal_title = "Meals Logged & On Track! 🎉"
            meal_msg = (
                f"Great job staying on top of your nutrition today, {first_name}! You've logged "
                f"{meals_count} meal(s) totaling {total_cals:,} kcal out of your {target_cals:,} kcal "
                f"daily target. Consistent food logging powers metabolic health."
            )

        # Remove any earlier meal milestone from today and insert fresh one with current timestamp
        db.query(Recommendation).filter(
            Recommendation.user_id == user_id,
            Recommendation.rule_id.in_(["milestone.meals_logged_on_track", "milestone.calories_met"]),
            Recommendation.created_at >= today_start,
        ).delete(synchronize_session=False)

        meal_rec = Recommendation(
            user_id=user_id,
            type="nutrition",
            severity="info",
            tier="primary_action",
            rule_id=meal_rule_id,
            title=meal_title,
            message=meal_msg,
            action_data={"action_label": "View Food Log", "route": "food-log.html"},
            created_at=now_naive,
        )
        db.add(meal_rec)
    else:
        # All meals were deleted for today — clean up meal milestone
        db.query(Recommendation).filter(
            Recommendation.user_id == user_id,
            Recommendation.rule_id.in_(["milestone.meals_logged_on_track", "milestone.calories_met"]),
            Recommendation.created_at >= today_start,
        ).delete(synchronize_session=False)

    db.commit()

    # 5. Evaluate full recommendation engine in background if tasks provided
    if background_tasks is not None:
        from app.database import SessionLocal

        def _bg_eval(uid: int):
            bg_db = SessionLocal()
            try:
                from recommendation_engine.recommendation_service import generate_and_persist_recommendations
                generate_and_persist_recommendations(uid, bg_db)
            except Exception:
                pass
            finally:
                bg_db.close()

        background_tasks.add_task(_bg_eval, user_id)

