"""
Splits dataset/raw/<class_name>/*.jpg into dataset/split/{train,val,test}/<class_name>/

Usage:
    python3 -m food_cv.data_prep

Expects:
    dataset/raw/jollof_rice/img1.jpg, img2.jpg, ...
    dataset/raw/egusi_soup/img1.jpg, ...
    (one folder per food class, named exactly as you want the class to appear)
"""

import random
import shutil

from PIL import Image

from . import config

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _list_images(class_dir):
    return [p for p in class_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS]


def _copy_or_convert(src_path, dest_dir):
    """Copies jpg/png as-is. Converts anything else (webp, bmp, gif, etc.)
    to .jpg so every downstream tool only ever has to deal with jpg/png."""
    if src_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        shutil.copy2(src_path, dest_dir / src_path.name)
    else:
        try:
            img = Image.open(src_path).convert("RGB")
            new_name = src_path.stem + ".jpg"
            img.save(dest_dir / new_name, "JPEG", quality=95)
        except Exception as exc:
            print(f"  WARNING: couldn't convert {src_path.name} ({exc}) — skipping")


def split_dataset():
    if not config.RAW_DATA_DIR.exists():
        raise FileNotFoundError(
            f"{config.RAW_DATA_DIR} doesn't exist. Create it and add one folder "
            "per food class, each containing that food's images."
        )

    class_dirs = [d for d in config.RAW_DATA_DIR.iterdir() if d.is_dir()]
    if not class_dirs:
        raise ValueError(f"No class folders found in {config.RAW_DATA_DIR}")

    if config.SPLIT_DATA_DIR.exists():
        shutil.rmtree(config.SPLIT_DATA_DIR)

    random.seed(config.SEED)
    summary = {}

    for class_dir in class_dirs:
        images = _list_images(class_dir)
        if len(images) < 10:
            print(f"WARNING: '{class_dir.name}' has only {len(images)} images — "
                  "aim for 50+ per class, ideally 150-300, for reliable training.")
        random.shuffle(images)

        n = len(images)
        n_train = int(n * config.TRAIN_RATIO)
        n_val = int(n * config.VAL_RATIO)

        splits = {
            "train": images[:n_train],
            "val": images[n_train:n_train + n_val],
            "test": images[n_train + n_val:],
        }

        for split_name, split_images in splits.items():
            out_dir = config.SPLIT_DATA_DIR / split_name / class_dir.name
            out_dir.mkdir(parents=True, exist_ok=True)
            for img_path in split_images:
                _copy_or_convert(img_path, out_dir)

        summary[class_dir.name] = {k: len(v) for k, v in splits.items()}

    print("\nDataset split complete:")
    for class_name, counts in summary.items():
        print(f"  {class_name}: train={counts['train']}, val={counts['val']}, test={counts['test']}")

    total = sum(sum(c.values()) for c in summary.values())
    print(f"\nTotal images: {total} across {len(summary)} classes")
    print(f"Output: {config.SPLIT_DATA_DIR}")


if __name__ == "__main__":
    split_dataset()