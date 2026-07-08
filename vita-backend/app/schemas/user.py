from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    age: int | None = None
    sex: Literal["male", "female", "other"] | None = None
    goal_type: Literal["weight_loss", "weight_gain", "maintenance"] | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str


class ProfileUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    sex: Literal["male", "female", "other"] | None = None
    height: float | None = None
    weight: float | None = None
    daily_calorie_target: int | None = None
    goal_type: Literal["weight_loss", "weight_gain", "maintenance"] | None = None
    dietary_restrictions: list[str] | None = None
    notification_preferences: dict | None = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    age: int | None
    sex: str | None
    height: float | None
    weight: float | None
    daily_calorie_target: int | None
    goal_type: str | None
    dietary_restrictions: list | None
    notification_preferences: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
