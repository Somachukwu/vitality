"""
Central config. Update CLASSES as you add food categories — everything
else (data prep, training, inference) reads from here so you only
change it in one place.
"""

from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent
RAW_DATA_DIR = BASE_DIR / "dataset" / "raw"        # drop your collected images here: raw/<class_name>/*.jpg
SPLIT_DATA_DIR = BASE_DIR / "dataset" / "split"    # auto-generated: split/train, split/val, split/test
MODEL_DIR = BASE_DIR / "trained_model"
MODEL_PATH = MODEL_DIR / "food_classifier.keras"
CLASS_INDICES_PATH = MODEL_DIR / "class_indices.json"

# --- Image / model params ---
IMAGE_SIZE = (224, 224)   # MobileNetV2's native input size
BATCH_SIZE = 16           # small default — safe for small datasets, raise if you have more data/GPU
SEED = 42

# --- Training ---
STAGE1_EPOCHS = 2   # train classification head only, base frozen
STAGE2_EPOCHS = 1   # fine-tune: unfreeze top N layers of the base model
FINE_TUNE_AT_LAYER = 100  # unfreeze layers from this index onwards in stage 2
STAGE1_LR = 1e-3
STAGE2_LR = 1e-5     # much lower — fine-tuning a pretrained model needs small steps

# --- Data split ratios (only used if you don't already have train/val/test folders) ---
TRAIN_RATIO = 0.7
VAL_RATIO = 0.15
TEST_RATIO = 0.15

# --- Classes ---
# Populate this with your actual food classes once your raw/ folders are named.
# Order doesn't matter — it's inferred from folder names at data-prep time,
# this list is just for reference/documentation.
CLASSES = [
    "akarabread",
    "banga",
    "bitterleaf",
    "edikakong",
    "egusi",
    "ewedu",
    "garriandgrounut",
    "jellof",
    "moimoi",
    "nkwobi",
    "ofeowerri",
    "ogbono",
    "okra",
    "pufpuf"
    # add more as you collect data
]
