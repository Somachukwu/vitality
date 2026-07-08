# Vitality — Food Recognition (Computer Vision)

Custom-trained MobileNetV2 transfer-learning model for Nigerian food
recognition, feeding directly into the recommendation engine.

## Why this approach (for your report)

Transfer learning on MobileNetV2 is the same approach used in the
published Nigerian food recognition literature:
- A 2022 study (IJARCCE) built "NaijaFood101" — 500 images across 10
  Nigerian food classes — and reached **97% accuracy** with MobileNetV2.
- Ataguba et al. (2024, *Human Behavior and Emerging Technologies*)
  combined Nigerian, Ghanaian, and Cameroonian food images (3,142 total)
  and reached **94.5% test accuracy**, also using transfer learning.

This means you don't need a massive dataset — 100-300 well-varied
images per class, with data augmentation, is consistent with published
results at this scope. Cite these papers in your literature review /
related works section; your project can position itself as extending
this line of work with a focus on the fusion + recommendation layer,
which those papers didn't build.

## Pipeline

1. **`config.py`** — all paths, image size, hyperparameters, and your class list in one place
2. **`data_prep.py`** — splits `dataset/raw/<class>/*.jpg` into train/val/test folders
3. **`train.py`** — two-stage transfer learning:
   - Stage 1: MobileNetV2 base frozen, train only the new classification head
   - Stage 2: unfreeze the top layers of the base, fine-tune at a much lower learning rate
4. **`evaluate.py`** — test accuracy, per-class precision/recall/F1, and a confusion matrix image (drop straight into your report)
5. **`inference.py`** — the function your backend actually calls: `recognize_food(image_path)`
6. **`nutrition_lookup.py`** — maps recognized class → calories/macros per typical serving

## How to use it

### 1. Collect and organize your images
Put your existing images into:
```
food_cv/dataset/raw/jollof_rice/*.jpg
food_cv/dataset/raw/egusi_soup/*.jpg
food_cv/dataset/raw/suya/*.jpg
...
```
One folder per dish, named exactly what you want the class to be called.
Aim for 100+ images per class if you can — more matters more than
anything else for accuracy. Mix your own photos with images collected
from the sources the literature used (YouTube keyframes, Google/Bing
Images, food vendor photos) to get variety in lighting/angle/plating.

There's also a public **Nigerian Food Dataset on Mendeley Data**
(10 classes, Bing-Images-sourced) you could merge in as a starting
point — worth checking its class list against yours.

### 2. Split the data
```bash
pip install -r requirements.txt
python3 -m food_cv.data_prep
```

### 3. Train
```bash
python3 -m food_cv.train
```
This needs a real GPU/Colab for reasonable speed — MobileNetV2
fine-tuning is light by deep learning standards but still slow on CPU
for more than a couple hundred images. Google Colab's free tier GPU is
enough for this scale.

### 4. Evaluate (for your report)
```bash
python3 -m food_cv.evaluate
```
Produces `trained_model/confusion_matrix.png` plus a printed
classification report.

### 5. Use it
```python
from food_cv.inference import recognize_food

result = recognize_food("meal_photo.jpg")
print(result)
# {'food_name': 'jollof_rice', 'confidence': 0.94, 'low_confidence': False,
#  'calories': 450, 'protein_g': 8, 'carbs_g': 75, 'fat_g': 12,
#  'serving_description': '1 plate (~300g)'}
```

### 6. Feed straight into the recommendation engine
```python
from food_cv.inference import recognize_food_to_food_log_entry
from datetime import datetime

entry = recognize_food_to_food_log_entry("meal_photo.jpg", timestamp=datetime.now())
# -> a FoodLogEntry, ready to pass into recommendation_engine.generate_recommendations()
```

## Important scope notes (document these in your report)

- **Portion size**: this system estimates "one typical serving" per
  dish, not true volumetric estimation from the image — that would need
  depth sensing or a reference object in-frame, out of scope here. The
  `portion_multiplier` param lets a user manually adjust if needed. This
  mirrors the simplification used in the published Nigerian food papers.
- **Nutrition values**: the numbers in `nutrition_lookup.py` are rough
  placeholders — **verify them against the Nigerian Food Composition
  Table (NFCT)** or another sourced reference before your defense, and
  cite that source in your report.
- **Low-confidence handling**: predictions under 60% confidence are
  flagged (`low_confidence: True`) so your frontend can prompt the user
  to confirm or correct the identified dish rather than silently
  logging a wrong guess.

## This sandbox couldn't run training/inference

TensorFlow isn't installed here and this environment has no network
access to install it, so `train.py`, `evaluate.py`, and `inference.py`
are untested in this session (I did test `data_prep.py` and
`nutrition_lookup.py` with synthetic data — both work). Run the full
pipeline on your own machine or Google Colab, and let me know if
anything breaks — happy to debug from an error message.
