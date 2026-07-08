import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.meal import Meal, MealItem
from app.models.user import User
from app.schemas.meal import MealOut

router = APIRouter(prefix="/food", tags=["food-recognition"])

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads" / "meals"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
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

    Upload a photo → get back the recognised dish, estimated calories and macros.
    Nothing is saved to the database yet — call POST /food/log to persist the meal.

    Response fields:
    - food_name           : predicted dish (e.g. "egusi")
    - confidence          : model confidence 0–1
    - low_confidence      : true if confidence < 0.6 (prompt user to confirm)
    - calories / protein_g / carbs_g / fat_g : per typical serving
    - serving_description : human-readable serving size used for the estimate
    """
    _validate_image(file)
    recognize_food = _load_recognizer()

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        result = recognize_food(tmp_path)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")
    finally:
        os.unlink(tmp_path)

    return result


@router.post("/log", response_model=MealOut, status_code=status.HTTP_201_CREATED)
async def log_meal_from_photo(
    file: UploadFile = File(..., description="Meal photo"),
    meal_type: str = Form(..., description="breakfast | lunch | dinner | snack"),
    portion_multiplier: float = Form(1.0, description="Scale factor for the estimated serving size (0.5 = half, 2.0 = double)"),
    notes: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 2 of the meal-logging flow (or call directly to do it in one shot).

    Upload a photo + meal metadata → recognise → save Meal + MealItem → return saved record.
    The photo is stored in uploads/meals/ and its URL is saved in the meal record so the
    frontend can display the thumbnail.
    """
    _validate_image(file)

    if meal_type not in VALID_MEAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"meal_type must be one of: {', '.join(sorted(VALID_MEAL_TYPES))}",
        )
    if not (0.1 <= portion_multiplier <= 10.0):
        raise HTTPException(status_code=422, detail="portion_multiplier must be between 0.1 and 10")

    recognize_food = _load_recognizer()

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    # Save image so the frontend can display the meal thumbnail later
    ext = Path(file.filename or "meal.jpg").suffix or ".jpg"
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

    pm = portion_multiplier
    now = datetime.now(timezone.utc)

    meal = Meal(
        user_id=current_user.id,
        meal_type=meal_type,
        logged_at=now,
        notes=notes,
        image_url=f"/uploads/meals/{filename}",
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

    db.commit()
    db.refresh(meal)
    return meal
