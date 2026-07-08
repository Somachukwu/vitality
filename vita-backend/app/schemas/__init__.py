from app.schemas.device import DeviceOut, DeviceRegister
from app.schemas.meal import MealCreate, MealItemIn, MealItemOut, MealOut
from app.schemas.recommendation import RecommendationCreate, RecommendationOut
from app.schemas.user import ProfileUpdate, TokenResponse, UserLogin, UserOut, UserRegister
from app.schemas.vitals import VitalsIngest, VitalsLatestOut, VitalsOut

__all__ = [
    "UserRegister", "UserLogin", "TokenResponse", "ProfileUpdate", "UserOut",
    "VitalsIngest", "VitalsOut", "VitalsLatestOut",
    "MealCreate", "MealItemIn", "MealItemOut", "MealOut",
    "RecommendationCreate", "RecommendationOut",
    "DeviceRegister", "DeviceOut",
]
