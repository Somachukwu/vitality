from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import SessionLocal, get_db
from app.models.meal import Meal, MealItem
from app.models.user import User
from app.schemas.meal import MealCreate, MealOut

router = APIRouter(prefix="/meals", tags=["meals"])


def _run_recommendation_background(user_id: int):
    """Evaluate recommendation engine in background after meal logging."""
    from recommendation_engine.recommendation_service import generate_and_persist_recommendations
    bg_db = SessionLocal()
    try:
        generate_and_persist_recommendations(user_id, bg_db)
    except Exception:
        pass
    finally:
        bg_db.close()


@router.post("/", response_model=MealOut, status_code=201)
def log_meal(
    body: MealCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_calories = sum(i.calories for i in body.items)
    total_carbs = sum(i.carbs for i in body.items)
    total_protein = sum(i.protein for i in body.items)
    total_fat = sum(i.fat for i in body.items)

    meal = Meal(
        user_id=current_user.id,
        meal_type=body.meal_type,
        logged_at=body.logged_at,
        notes=body.notes,
        total_calories=total_calories,
        total_carbs=total_carbs,
        total_protein=total_protein,
        total_fat=total_fat,
    )
    db.add(meal)
    db.flush()

    for item in body.items:
        db.add(MealItem(meal_id=meal.id, **item.model_dump()))

    # Auto-dismiss/purge any midday meal prompt for today since the user has logged a meal
    from datetime import datetime, timezone
    from app.models.recommendation import Recommendation
    from sqlalchemy import func
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = datetime.combine(now_naive.date(), datetime.min.time())

    # 1. If midday meal prompt was triggered earlier today, mark it read (preserves history for insights page)
    db.query(Recommendation).filter(
        Recommendation.user_id == current_user.id,
        Recommendation.rule_id == "time.midday_meal_prompt",
        Recommendation.created_at >= today_start,
        Recommendation.is_read == False,
    ).update({"is_read": True}, synchronize_session=False)

    # 2. Retire first-time user onboarding insight
    db.query(Recommendation).filter(
        Recommendation.user_id == current_user.id,
        Recommendation.rule_id == "lifestyle.set_daily_targets",
        Recommendation.is_read == False,
    ).update({"is_read": True}, synchronize_session=False)

    # 3. Calculate today's totals including the new meal
    today_meals = db.query(Meal).filter(
        Meal.user_id == current_user.id,
        Meal.logged_at >= today_start,
    ).all()
    meals_count = len(today_meals)
    total_cals = round(sum(m.total_calories for m in today_meals))
    target_cals = round(current_user.daily_calorie_target or 2200)
    first_name = current_user.name.split()[0] if current_user.name else "there"

    # 4. Trigger the fresh meal progress insight so it immediately takes the dashboard spotlight
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

    # Remove any existing meal milestone from earlier today and insert fresh one with current timestamp
    db.query(Recommendation).filter(
        Recommendation.user_id == current_user.id,
        Recommendation.rule_id.in_(["milestone.meals_logged_on_track", "milestone.calories_met"]),
        Recommendation.created_at >= today_start,
    ).delete(synchronize_session=False)

    meal_rec = Recommendation(
        user_id=current_user.id,
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

    db.commit()
    db.refresh(meal)
    background_tasks.add_task(_run_recommendation_background, current_user.id)
    return meal


@router.get("/", response_model=list[MealOut])
def get_meals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Meal)
        .filter(Meal.user_id == current_user.id)
        .order_by(Meal.logged_at.desc())
        .all()
    )


@router.delete("/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meal = db.query(Meal).filter(Meal.id == meal_id, Meal.user_id == current_user.id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    db.delete(meal)
    db.commit()
    background_tasks.add_task(_run_recommendation_background, current_user.id)
