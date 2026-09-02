"""
The single entry point your backend should call:

    from food_cv.inference import recognize_food

    result = recognize_food("/path/to/uploaded/meal_photo.jpg")
    # -> {
    #      "food_name": "jollof_rice",
    #      "confidence": 0.94,
    #      "calories": 450,
    #      "protein_g": 8, "carbs_g": 75, "fat_g": 12,
    #      "serving_description": "1 plate (~300g)",
    #    }

The output maps directly onto recommendation_engine.models.FoodLogEntry
(just add timestamp and multiply by the user's portion adjustment, if any)
so there's no translation layer needed between the two modules.
"""

import json
from functools import lru_cache

import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

from . import config
from .nutrition_lookup import get_nutrition

# Confidence below this threshold (55%) is treated as ambiguous and will not return a class name.
CONFIDENCE_THRESHOLD = 0.55
LOW_CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD


@lru_cache(maxsize=1)
def _load_model():
    model = tf.keras.models.load_model(config.MODEL_PATH)
    with open(config.CLASS_INDICES_PATH) as f:
        class_names = {int(k): v for k, v in json.load(f).items()}
    return model, class_names


def recognize_food(image_path: str) -> dict:
    model, class_names = _load_model()

    img = tf.keras.utils.load_img(image_path, target_size=config.IMAGE_SIZE)
    arr = tf.keras.utils.img_to_array(img)
    arr = preprocess_input(arr)
    batch = np.expand_dims(arr, axis=0)

    predictions = model.predict(batch, verbose=0)[0]
    top_idx = int(np.argmax(predictions))
    confidence = float(predictions[top_idx])
    raw_class = class_names[top_idx]

    # If confidence < 55%, treat as ambiguous and do not return class name
    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "food_name": None,
            "confidence": confidence,
            "is_ambiguous": True,
            "low_confidence": True,
            "calories": None,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "fiber_g": None,
            "serving_description": None,
        }

    nutrition = get_nutrition(raw_class)

    return {
        "food_name": raw_class,
        "confidence": confidence,
        "is_ambiguous": False,
        "low_confidence": False,
        "calories": nutrition.calories,
        "protein_g": nutrition.protein_g,
        "carbs_g": nutrition.carbs_g,
        "fat_g": nutrition.fat_g,
        "fiber_g": nutrition.fiber_g,
        "serving_description": nutrition.serving_description,
    }


def recognize_food_to_food_log_entry(image_path: str, timestamp, portion_multiplier: float = 1.0):
    """
    Convenience wrapper that returns a recommendation_engine.models.FoodLogEntry
    directly. Import is done lazily here so food_cv doesn't hard-depend on the
    recommendation_engine package unless you actually call this function.
    """
    from recommendation_engine.models import FoodLogEntry

    result = recognize_food(image_path)
    return FoodLogEntry(
        timestamp=timestamp,
        food_name=result["food_name"],
        calories=result["calories"] * portion_multiplier,
        protein_g=result["protein_g"] * portion_multiplier,
        carbs_g=result["carbs_g"] * portion_multiplier,
        fat_g=result["fat_g"] * portion_multiplier,
        portion_confidence=result["confidence"],
    )
