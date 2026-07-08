from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.meal import Meal, MealItem
from app.models.user import User
from app.schemas.meal import MealCreate, MealOut

router = APIRouter(prefix="/meals", tags=["meals"])


@router.post("/", response_model=MealOut, status_code=201)
def log_meal(
    body: MealCreate,
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

    db.commit()
    db.refresh(meal)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meal = db.query(Meal).filter(Meal.id == meal_id, Meal.user_id == current_user.id).first()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    db.delete(meal)
    db.commit()
