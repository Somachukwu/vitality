import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.meal import Meal, MealItem
from app.models.user import User
from app.schemas.meal import MealOut

router = APIRouter(prefix="/food", tags=["food-recognition"])
UPLOADS_DIR = settings.meals_upload_dir

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB
VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}


def _load_recognizer():
    """Lazy-import TensorFlow so the server starts even before the model is trained."""
    try:
        from food_cv.inference import recognize_food
        return recognize_food
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Food recognition model not found. "
                "Train it first: python -m food_cv.train"
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Food recognition model not ready: {exc}",
        )


def _validate_image(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{file.content_type}'. Send JPEG, PNG, or WebP.",
        )


def _configure_cloudinary() -> bool:
    if not settings.CLOUDINARY_URL:
        return False
    try:
        import re
        import cloudinary
        url = settings.CLOUDINARY_URL.strip()
        m = re.match(r"^cloudinary://([^:]+):([^@]+)@(.+)$", url)
        if m:
            api_key, api_secret, cloud_name = m.groups()
            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True
            )
            return True
        else:
            import os
            os.environ["CLOUDINARY_URL"] = url
            cloudinary.config()
            return True
    except Exception as e:
        print("Cloudinary configuration error:", e)
        return False


async def _upload_to_cloudinary(file_path: str) -> str | None:
    if not _configure_cloudinary():
        return None
    try:
        import asyncio
        import cloudinary.uploader
        res = await asyncio.to_thread(cloudinary.uploader.upload, file_path, folder="vitality_meals")
        return res.get("secure_url") if res else None
    except Exception as exc:
        print("Cloudinary upload warning:", exc)
        return None


# ── Schemas returned by this router ──────────────────────────────────────────

class AnalyzeResult:
    pass  # result is returned as a plain dict — no ORM needed


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_food_photo(
    file: UploadFile = File(..., description="Meal photo (JPEG / PNG / WebP, max 10 MB)"),
    current_user: User = Depends(get_current_user),
):
    """
    Step 1 of the meal-logging flow.

    Upload a photo → get back the recognised dish, estimated calories, macros, and image_url.
    Nothing is saved to the database yet — call POST /food/log to persist the meal.
    """
    _validate_image(file)
    recognize_food = _load_recognizer()

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    ext = Path(file.filename or "upload.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOADS_DIR / filename
    save_path.write_bytes(image_bytes)

    try:
        result = recognize_food(str(save_path))
    except KeyError as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")

    # Asynchronously upload to Cloudinary or fall back to local static URL
    cloud_url = await _upload_to_cloudinary(str(save_path))
    if cloud_url:
        result["image_url"] = cloud_url
        save_path.unlink(missing_ok=True)
    else:
        result["image_url"] = f"/uploads/meals/{filename}"

    # Flag uncertain matches (< 55% confidence) for the UI
    confidence = result.get("confidence", 1.0)
    result["uncertain_match"] = bool(confidence < 0.55)

    return result


@router.post("/log", response_model=MealOut, status_code=status.HTTP_201_CREATED)
async def log_meal_from_photo(
    file: UploadFile | None = File(None, description="Meal photo (optional if image_url provided)"),
    image_url: str | None = Form(None, description="Pre-uploaded image URL from /analyze"),
    meal_type: str = Form(..., description="breakfast | lunch | dinner | snack"),
    portion_multiplier: float = Form(1.0, description="Scale factor for serving size"),
    food_name: str | None = Form(None, description="Optionally override recognised dish name"),
    predicted_food_name: str | None = Form(None, description="Original predicted dish name from model"),
    prediction_confidence: float | None = Form(None, description="Original prediction confidence"),
    notes: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 2 of the meal-logging flow (or call directly to do it in one shot).

    Saves Meal + MealItem → records active learning feedback → returns saved record.
    """
    if meal_type not in VALID_MEAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"meal_type must be one of: {', '.join(sorted(VALID_MEAL_TYPES))}",
        )
    if not (0.1 <= portion_multiplier <= 10.0):
        raise HTTPException(status_code=422, detail="portion_multiplier must be between 0.1 and 10")

    recognize_food = _load_recognizer()
    final_image_url = image_url
    result = None

    if file and file.filename:
        _validate_image(file)
        image_bytes = await file.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

        ext = Path(file.filename or "meal.jpg").suffix or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        save_path = UPLOADS_DIR / filename
        save_path.write_bytes(image_bytes)

        try:
            result = recognize_food(str(save_path))
        except Exception as exc:
            save_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Inference error: {exc}")

        if not final_image_url:
            cloud_url = await _upload_to_cloudinary(str(save_path))
            if cloud_url:
                final_image_url = cloud_url
                save_path.unlink(missing_ok=True)
            else:
                final_image_url = f"/uploads/meals/{filename}"

    # If food_name provided without result dict, perform lookup or fallback
    if not result:
        from food_cv.nutrition_lookup import get_nutrition
        dish = food_name or "jollof_rice"
        nutrition = get_nutrition(dish)
        result = {
            "food_name": dish,
            "calories": nutrition.calories,
            "protein_g": nutrition.protein_g,
            "carbs_g": nutrition.carbs_g,
            "fat_g": nutrition.fat_g,
            "serving_description": nutrition.serving_description,
        }

    pm = portion_multiplier
    now = datetime.now(timezone.utc)

    # 1. Persist Meal & MealItem
    meal = Meal(
        user_id=current_user.id,
        meal_type=meal_type,
        logged_at=now,
        notes=notes,
        image_url=final_image_url or "/uploads/meals/default.jpg",
        total_calories=round(result["calories"] * pm, 1),
        total_carbs=round(result["carbs_g"] * pm, 1),
        total_protein=round(result["protein_g"] * pm, 1),
        total_fat=round(result["fat_g"] * pm, 1),
    )
    db.add(meal)
    db.flush()

    db.add(MealItem(
        meal_id=meal.id,
        food_name=result["food_name"],
        portion_size=result["serving_description"],
        calories=round(result["calories"] * pm, 1),
        carbs=round(result["carbs_g"] * pm, 1),
        protein=round(result["protein_g"] * pm, 1),
        fat=round(result["fat_g"] * pm, 1),
    ))

    # 2. Record Active Learning Feedback if prediction metadata is present
    if predicted_food_name or final_image_url:
        from app.models.food_feedback import FoodFeedback
        pred_class = predicted_food_name or result["food_name"]
        conf_val = float(prediction_confidence) if prediction_confidence is not None else 1.0
        corrected_name = result["food_name"] if result["food_name"] != pred_class else None

        db.add(FoodFeedback(
            user_id=current_user.id,
            image_url=final_image_url or "",
            predicted_class=pred_class,
            confidence=conf_val,
            user_confirmed=corrected_name is None,
            user_corrected_class=corrected_name,
            user_portion_multiplier=pm,
        ))

    db.commit()
    db.refresh(meal)
    return meal

