from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MealItemIn(BaseModel):
    food_name: str
    portion_size: str | None = None
    calories: float = 0.0
    carbs: float = 0.0
    protein: float = 0.0
    fat: float = 0.0


class MealCreate(BaseModel):
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    logged_at: datetime
    notes: str | None = None
    items: list[MealItemIn] = []


class MealItemOut(MealItemIn):
    id: int
    model_config = {"from_attributes": True}


class MealOut(BaseModel):
    id: int
    meal_type: str
    total_calories: float
    total_carbs: float
    total_protein: float
    total_fat: float
    image_url: str | None
    notes: str | None
    logged_at: datetime
    items: list[MealItemOut] = []

    model_config = {"from_attributes": True}
