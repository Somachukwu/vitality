"""
EXAMPLE ONLY — shows how to plug generate_recommendations() into a
FastAPI route. Copy the relevant pieces into your actual backend;
don't import this file directly, since it assumes your own DB layer
functions (fetch_user_profile, fetch_vitals_for_day, etc.) exist.

If you're on Flask instead of FastAPI, the logic inside the handler
function is identical — only the route decorator and request/response
plumbing changes.
"""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .recommendation_service import generate_recommendations, recommendations_to_dict

# --- Replace these with your actual data-access functions ---
# from your_app.db import (
#     fetch_user_profile,
#     fetch_vitals_for_day,
#     fetch_food_logs_for_day,
#     fetch_recent_snapshots,
# )

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationRequest(BaseModel):
    user_id: str
    day: date


@router.post("/generate")
def generate(request: RecommendationRequest):
    profile = fetch_user_profile(request.user_id)  # -> UserProfile
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")

    vitals = fetch_vitals_for_day(request.user_id, request.day)  # -> list[VitalsReading]
    food_logs = fetch_food_logs_for_day(request.user_id, request.day)  # -> list[FoodLogEntry]
    history = fetch_recent_snapshots(request.user_id, before=request.day, limit=30)  # -> list[DailySnapshot]

    recs = generate_recommendations(
        profile=profile,
        day=request.day,
        vitals=vitals,
        food_logs=food_logs,
        history=history,
    )

    return {"user_id": request.user_id, "day": str(request.day), "recommendations": recommendations_to_dict(recs)}
