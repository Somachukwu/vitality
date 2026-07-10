import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { formatDate, toast, initLucide, applyStoredTheme, initThemeToggle } from './utils.js';
import { NIGERIAN_FOODS } from './mock.js';
import { api, resolveApiUrl } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('food-log.html');
initThemeToggle();

const fileInput   = document.getElementById('file');
const dropzone    = document.getElementById('dropzone');
const preview     = document.getElementById('preview');
const previewWrap = document.getElementById('preview-wrap');
const result      = document.getElementById('result');
const overlay     = document.getElementById('overlay');
let selectedFile  = null;
let lastDetection = null;

['dragenter', 'dragover'].forEach(ev => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add('dragover'); }));
['dragleave', 'drop'].forEach(ev => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove('dragover'); }));
dropzone.addEventListener('drop', (e) => { const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); });
fileInput.addEventListener('change', (e) => { const f = e.target.files?.[0]; if (f) handleFile(f); });

function handleFile(f) {
  if (!/^image\/(jpeg|png)$/.test(f.type)) return toast('Please choose a JPEG or PNG image.', 'error');
  if (f.size > 10 * 1024 * 1024) return toast('Image must be 10 MB or less.', 'error');
  selectedFile = f;
  preview.src = URL.createObjectURL(f);
  previewWrap.classList.remove('hidden');
  result.classList.add('hidden');
}

document.getElementById('clear-btn').addEventListener('click', () => {
  selectedFile = null; fileInput.value = ''; previewWrap.classList.add('hidden'); result.classList.add('hidden');
});

function formatFoodName(name) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

document.getElementById('analyze-btn').addEventListener('click', async () => {
  if (!selectedFile) return;
  const multiplier = Math.max(0.25, parseFloat(document.getElementById('portion-size').value) || 1);
  overlay.classList.remove('hidden');
  try {
    const formData = new FormData();
    formData.append('file', selectedFile);
    const r = await api.postForm('/food/analyze', formData);
    lastDetection = {
      multiplier,
      confidence: r.confidence,
      lowConfidence: r.low_confidence,
      detectedFoods: [{
        name: formatFoodName(r.food_name),
        portionSize: multiplier === 1 ? r.serving_description : `${multiplier}× ${r.serving_description}`,
        calories: Math.round(r.calories * multiplier),
        carbs:    Math.round(r.carbs_g  * multiplier),
        protein:  Math.round(r.protein_g * multiplier),
        fat:      Math.round(r.fat_g    * multiplier),
      }],
    };
    renderResult(lastDetection);
  } catch (err) {
    toast('Could not analyze photo: ' + err.message, 'error');
  } finally {
    overlay.classList.add('hidden');
  }
});

function renderResult(d) {
  const total  = d.detectedFoods.reduce((s, f) => s + f.calories, 0);
  const macros = d.detectedFoods.reduce((a, f) => ({ carbs: a.carbs + f.carbs, protein: a.protein + f.protein, fat: a.fat + f.fat }), { carbs: 0, protein: 0, fat: 0 });
  result.classList.remove('hidden');
  result.innerHTML = `
    <div class="card">
      <div class="row between mb-1">
        <div class="card-title">Recognized</div>
        <span class="badge ${d.lowConfidence ? 'badge-warning' : 'badge-success'}">Confidence ${Math.round(d.confidence * 100)}%</span>
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
        <label for="food-search">Pick the correct item</label>
        <input id="food-search" list="ng-foods" placeholder="Start typing a Nigerian food…" />
        <datalist id="ng-foods">${NIGERIAN_FOODS.map(n => `<option value="${n}"></option>`).join('')}</datalist>
        <p class="text-xs muted mt-1">Your correction helps the model learn over time.</p>
      </div>
    </div>
  `;
  initLucide();

  document.getElementById('confirm-btn').addEventListener('click', async () => {
    const hour = new Date().getHours();
    const mealType = hour < 11 ? 'breakfast' : hour < 15 ? 'lunch' : hour < 19 ? 'dinner' : 'snack';
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('meal_type', mealType);
      formData.append('portion_multiplier', String(d.multiplier));
      await api.postForm('/food/log', formData);
      await loadMeals();
      toast('Meal added to your log');
      document.getElementById('clear-btn').click();
    } catch (err) {
      toast('Could not save meal: ' + err.message, 'error');
    }
  });

  document.getElementById('correct-btn').addEventListener('click', () => {
    document.getElementById('correct-panel').classList.toggle('hidden');
  });
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
  const filtered = filterDate ? meals.filter(m => m.timestamp.slice(0, 10) === filterDate) : meals;
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
