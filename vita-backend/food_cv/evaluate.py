"""
Evaluates the trained model on the held-out test set and produces:
- overall test accuracy
- per-class precision/recall/F1 (classification_report)
- a confusion matrix image saved to trained_model/confusion_matrix.png

This is the output you'll want to screenshot straight into Chapter 4/5
of your project report — it's the same evaluation style used in the
Nigerian food recognition papers.

Usage:
    python3 -m food_cv.evaluate
"""

import json

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from sklearn.metrics import ConfusionMatrixDisplay, classification_report
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

from . import config


def evaluate():
    model = tf.keras.models.load_model(config.MODEL_PATH)
    with open(config.CLASS_INDICES_PATH) as f:
        class_names = [v for _, v in sorted(json.load(f).items(), key=lambda kv: int(kv[0]))]

    test_ds = tf.keras.utils.image_dataset_from_directory(
        config.SPLIT_DATA_DIR / "test",
        image_size=config.IMAGE_SIZE,
        batch_size=config.BATCH_SIZE,
        shuffle=False,
        label_mode="categorical",
    )
    test_ds_prepped = test_ds.map(lambda x, y: (preprocess_input(x), y))

    y_true = np.concatenate([np.argmax(y.numpy(), axis=1) for _, y in test_ds])
    y_pred_probs = model.predict(test_ds_prepped)
    y_pred = np.argmax(y_pred_probs, axis=1)

    print("\n=== Classification report ===")
    print(classification_report(y_true, y_pred, target_names=class_names))

    test_loss, test_acc = model.evaluate(test_ds_prepped)
    print(f"Test accuracy: {test_acc:.4f}")

    fig, ax = plt.subplots(figsize=(10, 10))
    ConfusionMatrixDisplay.from_predictions(
        y_true, y_pred, display_labels=class_names, xticks_rotation=45, ax=ax, colorbar=False
    )
    plt.tight_layout()
    out_path = config.MODEL_DIR / "confusion_matrix.png"
    plt.savefig(out_path, dpi=150)
    print(f"Saved confusion matrix to {out_path}")


if __name__ == "__main__":
    evaluate()
