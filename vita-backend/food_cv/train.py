"""
Two-stage transfer learning on MobileNetV2, matching the standard approach
used in the Nigerian/African food recognition literature (Ataguba et al.
2024, NaijaFood101 paper — both used MobileNetV2 and got 94-97% accuracy
on comparably small datasets).

Stage 1: freeze the MobileNetV2 base, train only the new classification
          head. This adapts fast and won't destroy the pretrained features.
Stage 2: unfreeze the top N layers of the base and fine-tune with a much
          smaller learning rate. This lets the model adapt its higher-level
          features specifically to Nigerian dishes (texture, color, plating).

Usage:
    python3 -m food_cv.data_prep      # run once, or whenever raw/ changes
    python3 -m food_cv.train
"""

import json

import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

from . import config


def _make_datasets():
    train_ds = tf.keras.utils.image_dataset_from_directory(
        config.SPLIT_DATA_DIR / "train",
        image_size=config.IMAGE_SIZE,
        batch_size=config.BATCH_SIZE,
        seed=config.SEED,
        label_mode="categorical",
    )
    val_ds = tf.keras.utils.image_dataset_from_directory(
        config.SPLIT_DATA_DIR / "val",
        image_size=config.IMAGE_SIZE,
        batch_size=config.BATCH_SIZE,
        seed=config.SEED,
        label_mode="categorical",
    )

    class_names = train_ds.class_names

    augmentation = tf.keras.Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.1),
        layers.RandomZoom(0.15),
        layers.RandomContrast(0.1),
    ])

    def prep(ds, training):
        if training:
            ds = ds.map(lambda x, y: (augmentation(x, training=True), y))
        ds = ds.map(lambda x, y: (preprocess_input(x), y))
        return ds.prefetch(tf.data.AUTOTUNE)

    return prep(train_ds, training=True), prep(val_ds, training=False), class_names


def build_model(num_classes: int):
    base = MobileNetV2(
        input_shape=(*config.IMAGE_SIZE, 3),
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False  # Stage 1: frozen

    inputs = tf.keras.Input(shape=(*config.IMAGE_SIZE, 3))
    x = base(inputs, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs, outputs)
    return model, base


def train():
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    train_ds, val_ds, class_names = _make_datasets()
    num_classes = len(class_names)
    print(f"Training on {num_classes} classes: {class_names}")

    model, base = build_model(num_classes)

    # --- Stage 1: train head only ---
    model.compile(
        optimizer=tf.keras.optimizers.Adam(config.STAGE1_LR),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    print("\n=== Stage 1: training classification head (base frozen) ===")
    model.fit(train_ds, validation_data=val_ds, epochs=config.STAGE1_EPOCHS)

    # --- Stage 2: fine-tune top layers of the base ---
    base.trainable = True
    for layer in base.layers[: config.FINE_TUNE_AT_LAYER]:
        layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(config.STAGE2_LR),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    print("\n=== Stage 2: fine-tuning top layers ===")
    model.fit(train_ds, validation_data=val_ds, epochs=config.STAGE2_EPOCHS)

    model.save(config.MODEL_PATH)
    with open(config.CLASS_INDICES_PATH, "w") as f:
        json.dump({i: name for i, name in enumerate(class_names)}, f, indent=2)

    print(f"\nSaved model to {config.MODEL_PATH}")
    print(f"Saved class index mapping to {config.CLASS_INDICES_PATH}")


if __name__ == "__main__":
    train()
