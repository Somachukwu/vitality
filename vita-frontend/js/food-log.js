import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { formatDate, toast, initLucide, applyStoredTheme, initThemeToggle, compressImage, getLocalTimestampDate } from './utils.js';
import { NIGERIAN_FOODS } from './mock.js';
import { api, resolveApiUrl } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('food-log.html');
initThemeToggle();

const cameraFileInput  = document.getElementById('camera-file');
const galleryFileInput = document.getElementById('gallery-file');
const dropzone         = document.getElementById('dropzone');
const optionModal      = document.getElementById('option-modal');
const modalCameraBtn   = document.getElementById('modal-camera-btn');
const modalGalleryBtn  = document.getElementById('modal-gallery-btn');
const modalCancelBtn   = document.getElementById('modal-cancel-btn');
const preview          = document.getElementById('preview');
const previewWrap      = document.getElementById('preview-wrap');
const result           = document.getElementById('result');
const overlay          = document.getElementById('overlay');
let selectedFile       = null;
let lastDetection      = null;

// --- On-Device AI Model (ONNX Runtime Web) Configuration ---
const CLASS_MAPPING = {
  0: "abacha",
  1: "beans",
  2: "fried rice",
  3: "akara",
  4: "banga",
  5: "bitterleaf",
  6: "egusi",
  7: "ewedu",
  8: "jellof",
  9: "moimoi",
  10: "ofeowerri",
  11: "ogbono",
  12: "okra",
  13: "pufpuf",
  14: "spaghetti"
};

const NUTRITION_TABLE = {
  abacha:       { calories: 430.4, protein_g: 14.30, carbs_g: 62.70, fat_g: 13.60, serving_description: "per 100 g" },
  "fried rice": { calories: 172.88, protein_g: 2.56, carbs_g: 32.55, fat_g: 3.36, serving_description: "per 100 g" },
  akara:        { calories: 218.0, protein_g: 12.07, carbs_g: 23.76, fat_g: 8.30, serving_description: "per 100 g" },
  banga:        { calories: 131.7, protein_g: 13.61, carbs_g: 1.36, fat_g: 7.98, serving_description: "per 100 g" },
  bitterleaf:   { calories: 179.0, protein_g: 9.40, carbs_g: 14.20, fat_g: 9.40, serving_description: "per 100 g" },
  egusi:        { calories: 179.5, protein_g: 8.59, carbs_g: 1.95, fat_g: 15.26, serving_description: "per 100 g" },
  ewedu:        { calories: 37.0,  protein_g: 2.00, carbs_g: 5.00, fat_g: 1.00, serving_description: "per 100 g" },
  beans:        { calories: 147.56, protein_g: 11.605, carbs_g: 21.52, fat_g: 0.496, serving_description: "per 100 g" },
  jellof:       { calories: 144.545, protein_g: 2.635, carbs_g: 27.505, fat_g: 2.665, serving_description: "per 100 g" },
  moimoi:       { calories: 108.406, protein_g: 6.47, carbs_g: 15.74, fat_g: 2.174, serving_description: "per 100 g" },
  ofeowerri:    { calories: 438.0, protein_g: 28.00, carbs_g: 14.00, fat_g: 30.00, serving_description: "per 100 g" },
  ogbono:       { calories: 227.0, protein_g: 11.14, carbs_g: 0.74, fat_g: 19.94, serving_description: "per 100 g" },
  okra:         { calories: 172.3, protein_g: 11.17, carbs_g: 4.44, fat_g: 12.21, serving_description: "per 100 g" },
  pufpuf:       { calories: 242.0, protein_g: 5.00, carbs_g: 51.00, fat_g: 2.00, serving_description: "per 100 g" },
  spaghetti:    { calories: 123.5, protein_g: 4.20, carbs_g: 26.00, fat_g: 0.30, serving_description: "per 100 g" },
};

function getDishNutrition(name) {
  const key = (name || "").toLowerCase().trim().replace(/_/g, " ");
  if (NUTRITION_TABLE[key]) return NUTRITION_TABLE[key];
  for (const [k, v] of Object.entries(NUTRITION_TABLE)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return { calories: 200, protein_g: 5, carbs_g: 30, fat_g: 5, serving_description: "per 100 g" };
}

let ortSession = null;
let modelLoadingPromise = null;

async function initOnDeviceModel() {
  if (ortSession) return ortSession;
  if (modelLoadingPromise) return modelLoadingPromise;

  modelLoadingPromise = (async () => {
    if (typeof ort === 'undefined') {
      console.warn('ONNX Runtime Web library not found on page.');
      return null;
    }
    try {
      if (ort.env && ort.env.wasm) {
        ort.env.wasm.numThreads = 1;
        ort.env.wasm.simd = true;
      }
      const modelUrl = new URL('models/food_classifier/food_classifier.onnx', window.location.href).href;
      ortSession = await ort.InferenceSession.create(modelUrl, {
        executionProviders: ['wasm', 'webgl']
      });
      console.log('On-device food recognition model loaded successfully.');
      return ortSession;
    } catch (err) {
      console.warn('Could not load on-device ONNX model:', err);
      return null;
    } finally {
      modelLoadingPromise = null;
    }
  })();

  return modelLoadingPromise;
}

// Pre-load on-device AI in background on page load
initOnDeviceModel();

async function runOnDeviceInference(imgElement) {
  const session = await initOnDeviceModel();
  if (!session) {
    throw new Error('On-device AI model is not available.');
  }

  const canvas = document.createElement('canvas');
  canvas.width = 224;
  canvas.height = 224;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(imgElement, 0, 0, 224, 224);
  const imgData = ctx.getImageData(0, 0, 224, 224);
  const { data } = imgData;

  // Preprocess into Float32Array [1, 224, 224, 3] with MobileNetV2 normalization: (pixel / 127.5) - 1.0
  const floatData = new Float32Array(1 * 224 * 224 * 3);
  let p = 0;
  for (let i = 0; i < data.length; i += 4) {
    floatData[p++] = (data[i]     / 127.5) - 1.0;
    floatData[p++] = (data[i + 1] / 127.5) - 1.0;
    floatData[p++] = (data[i + 2] / 127.5) - 1.0;
  }

  const inputName = session.inputNames[0] || 'input';
  const tensor = new ort.Tensor('float32', floatData, [1, 224, 224, 3]);
  const feeds = { [inputName]: tensor };
  const results = await session.run(feeds);
  const outputName = session.outputNames[0] || 'food_class';
  const output = results[outputName].data;

  let maxIdx = 0;
  let maxConf = output[0];
  for (let i = 1; i < output.length; i++) {
    if (output[i] > maxConf) {
      maxConf = output[i];
      maxIdx = i;
    }
  }

  return {
    food_name: CLASS_MAPPING[maxIdx] || 'unknown',
    confidence: maxConf
  };
}

dropzone.addEventListener('click', () => {
  optionModal.classList.remove('hidden');
  initLucide();
});

modalCancelBtn.addEventListener('click', () => {
  optionModal.classList.add('hidden');
});

modalCameraBtn.addEventListener('click', () => {
  optionModal.classList.add('hidden');
  cameraFileInput.click();
});

modalGalleryBtn.addEventListener('click', () => {
  optionModal.classList.add('hidden');
  galleryFileInput.click();
});

optionModal.addEventListener('click', (e) => {
  if (e.target === optionModal) {
    optionModal.classList.add('hidden');
  }
});

['dragenter', 'dragover'].forEach(ev => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add('dragover'); }));
['dragleave', 'drop'].forEach(ev => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove('dragover'); }));
dropzone.addEventListener('drop', (e) => { const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); });
cameraFileInput.addEventListener('change', (e) => { const f = e.target.files?.[0]; if (f) handleFile(f); });
galleryFileInput.addEventListener('change', (e) => { const f = e.target.files?.[0]; if (f) handleFile(f); });

async function handleFile(f) {
  if (!f || !f.type.startsWith('image/')) {
    return toast('Please select an image file.', 'error');
  }
  if (optionModal) optionModal.classList.add('hidden');
  let fileToUse = f;
  try {
    fileToUse = await compressImage(f);
  } catch (err) {
    console.warn('Compression error, fallback to original:', err);
  }
  selectedFile = fileToUse;
  preview.src = URL.createObjectURL(fileToUse);
  previewWrap.classList.remove('hidden');
  result.classList.add('hidden');
}

document.getElementById('clear-btn').addEventListener('click', () => {
  selectedFile = null;
  cameraFileInput.value = '';
  galleryFileInput.value = '';
  previewWrap.classList.add('hidden');
  result.classList.add('hidden');
});

function formatFoodName(name) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

document.getElementById('analyze-btn').addEventListener('click', async () => {
  if (!selectedFile) return;
  const multiplier = Math.max(0.25, parseFloat(document.getElementById('portion-size').value) || 1);
  overlay.classList.remove('hidden');
  try {
    let food_name = null;
    let confidence = 0;

    try {
      const pred = await runOnDeviceInference(preview);
      food_name = pred.food_name;
      confidence = pred.confidence;
    } catch (localErr) {
      console.warn('On-device inference fallback:', localErr);
      const formData = new FormData();
      formData.append('file', selectedFile);
      const r = await api.postForm('/food/analyze', formData);
      food_name = r.food_name;
      confidence = r.confidence || 0;
    }

    const isAmbiguous = Boolean(!food_name || confidence < 0.55);
    const nutrition = getDishNutrition(food_name);

    lastDetection = {
      imageUrl: null,
      multiplier,
      confidence,
      isAmbiguous,
      detectedFoods: (!isAmbiguous && food_name) ? [{
        name: formatFoodName(food_name),
        portionSize: multiplier === 1 ? nutrition.serving_description : `${multiplier}× ${nutrition.serving_description}`,
        calories: Math.round((nutrition.calories || 0) * multiplier),
        carbs:    Math.round((nutrition.carbs_g  || 0) * multiplier),
        protein:  Math.round((nutrition.protein_g || 0) * multiplier),
        fat:      Math.round((nutrition.fat_g    || 0) * multiplier),
      }] : [],
    };
    renderResult(lastDetection);
  } catch (err) {
    toast('Could not analyze photo: ' + err.message, 'error');
  } finally {
    overlay.classList.add('hidden');
  }
});

function renderResult(d) {
  result.classList.remove('hidden');

  if (d.isAmbiguous) {
    result.innerHTML = `
      <div class="card">
        <div class="row between mb-1 align-center">
          <div class="card-title" style="color:var(--amber); margin-bottom:0">Ambiguous / Unrecognized</div>
          <span class="badge badge-warning">Confidence ${Math.round(d.confidence * 100)}% (&lt; 55%)</span>
        </div>
        <p class="text-sm muted mb-2">
          The photo could not be identified with high confidence (threshold is 55%). Please select or type what you ate below:
        </p>
        <div class="mb-2">
          <label for="food-search" style="font-weight:600; display:block; margin-bottom:0.35rem">Select or type food name</label>
          <input id="food-search" list="ng-foods" placeholder="Type a Nigerian food (e.g. Jollof Rice, Egusi, Akara)..." style="width:100%" autofocus />
          <datalist id="ng-foods">${NIGERIAN_FOODS.map(n => `<option value="${n}"></option>`).join('')}</datalist>
        </div>
        <div class="row gap-sm mt-2 flex-wrap">
          <button class="btn btn-primary" id="confirm-btn"><i data-lucide="check"></i> Add to log</button>
        </div>
      </div>
    `;
  } else {
    const total  = d.detectedFoods.reduce((s, f) => s + f.calories, 0);
    const macros = d.detectedFoods.reduce((a, f) => ({ carbs: a.carbs + f.carbs, protein: a.protein + f.protein, fat: a.fat + f.fat }), { carbs: 0, protein: 0, fat: 0 });
    result.innerHTML = `
      <div class="card">
        <div class="row between mb-1 align-center">
          <div class="card-title" style="margin-bottom:0">Recognized</div>
          <span class="badge badge-success">Confidence ${Math.round(d.confidence * 100)}%</span>
        </div>
        <div class="list">
          ${d.detectedFoods.map(f => `
            <div class="list-item">
              <div style="flex:1">
                <div style="font-weight:600">${f.name}</div>
                <div class="text-xs muted">${f.portionSize} · ${f.carbs}g C · ${f.protein}g P · ${f.fat}g F</div>
              </div>
              <div class="num" style="font-weight:600">${f.calories}<span class="text-xs muted"> kcal</span></div>
            </div>
          `).join('')}
        </div>
        <div class="row between mt-2"><strong>Total</strong><span class="num" style="font-weight:600">${total} kcal · ${macros.carbs}g C · ${macros.protein}g P · ${macros.fat}g F</span></div>
        <div class="row gap-sm mt-2 flex-wrap">
          <button class="btn btn-primary" id="confirm-btn"><i data-lucide="check"></i> Add to log</button>
          <button class="btn btn-ghost" id="correct-btn"><i data-lucide="pencil"></i> Did we get this right?</button>
        </div>
        <div id="correct-panel" class="hidden mt-2">
          <label for="food-search" style="font-weight:600; display:block; margin-bottom:0.35rem">Pick the correct item</label>
          <input id="food-search" list="ng-foods" placeholder="Start typing a Nigerian food…" style="width:100%" />
          <datalist id="ng-foods">${NIGERIAN_FOODS.map(n => `<option value="${n}"></option>`).join('')}</datalist>
          <p class="text-xs muted mt-1">Your correction helps the model learn over time.</p>
        </div>
      </div>
    `;
  }

  initLucide();

  const confirmBtn = document.getElementById('confirm-btn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', async () => {
      if (confirmBtn.disabled) return;

      const hour = new Date().getHours();
      const mealType = hour < 11 ? 'breakfast' : hour < 15 ? 'lunch' : hour < 19 ? 'dinner' : 'snack';
      
      let chosenFood = document.getElementById('food-search')?.value?.trim();
      if (!chosenFood && d.isAmbiguous) {
        return toast('Please select or type a food name to add to log.', 'error');
      }
      if (!chosenFood && d.detectedFoods?.[0]?.name) {
        chosenFood = d.detectedFoods[0].name;
      }

      const originalHtml = confirmBtn.innerHTML;
      confirmBtn.disabled = true;
      confirmBtn.innerHTML = '<span style="display:inline-block; width:14px; height:14px; border:2px solid currentColor; border-top-color:transparent; border-radius:50%; animation:spin 0.7s linear infinite; vertical-align:middle; margin-right:6px"></span>Adding to log…';

      try {
        const formData = new FormData();
        if (d.imageUrl) {
          formData.append('image_url', d.imageUrl);
          if (chosenFood) {
            formData.append('food_name', chosenFood.toLowerCase().replace(/ /g, '_'));
          }
        } else if (selectedFile) {
          formData.append('file', selectedFile);
          if (chosenFood) {
            formData.append('food_name', chosenFood.toLowerCase().replace(/ /g, '_'));
          }
        }
        if (d.detectedFoods?.[0]?.name) {
          formData.append('predicted_food_name', d.detectedFoods[0].name.toLowerCase().replace(/ /g, '_'));
        }
        if (d.confidence) {
          formData.append('prediction_confidence', String(d.confidence));
        }
        formData.append('meal_type', mealType);
        formData.append('portion_multiplier', String(d.multiplier));
        await api.postForm('/food/log', formData);
        await loadMeals();
        toast('Meal added to your log');
        document.getElementById('clear-btn').click();
      } catch (err) {
        toast('Could not save meal: ' + err.message, 'error');
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = originalHtml;
        initLucide();
      }
    });
  }

  const correctBtn = document.getElementById('correct-btn');
  if (correctBtn) {
    correctBtn.addEventListener('click', () => {
      document.getElementById('correct-panel')?.classList.toggle('hidden');
    });
  }
}

const dateFilter = document.getElementById('date-filter');
dateFilter.addEventListener('change', renderHistory);

let meals = [];

async function loadMeals() {
  try {
    const raw = await api.get('/meals/');
    meals = raw.map(m => ({
      id:            m.id,
      timestamp:     m.logged_at,
      imageUrl:      resolveApiUrl(m.image_url) || null,
      totalCalories: m.total_calories,
      detectedFoods: (m.items || []).map(i => ({ name: i.food_name, portionSize: i.portion_size, calories: i.calories, carbs: i.carbs, protein: i.protein, fat: i.fat })),
    }));
  } catch {
    meals = [];
  }
  renderHistory();
}

function renderHistory() {
  const host = document.getElementById('history');
  const filterDate = dateFilter.value;
  const filtered = filterDate ? meals.filter(m => getLocalTimestampDate(m.timestamp) === filterDate) : meals;
  if (!filtered.length) {
    host.innerHTML = `<div class="card center muted">No meals for this day.</div>`;
    return;
  }
  host.innerHTML = filtered.map(m => `
    <div class="list-item">
      ${m.imageUrl ? `<img src="${m.imageUrl}" alt="" class="meal-thumb" loading="lazy"/>` : '<div class="meal-thumb" style="background:var(--surface-2)"></div>'}
      <div style="flex:1; min-width:0">
        <div style="font-weight:600">${m.detectedFoods.map(f => f.name).join(', ') || 'Meal'}</div>
        <div class="text-xs muted">${formatDate(m.timestamp)}</div>
      </div>
      <div class="num" style="font-weight:600">${m.totalCalories}<span class="text-xs muted"> kcal</span></div>
    </div>
  `).join('');
}

loadMeals();
