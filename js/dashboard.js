import { requireAuth, getUser, saveUser } from './auth.js';
import { renderNav } from './nav.js';
import { countUp, vitalsStatus, statusDot, formatTime, toast, applyStoredTheme, toggleTheme, initLucide, waitForChart } from './utils.js';
import { api, resolveApiUrl } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('dashboard.html');

let user = getUser();
document.getElementById('hello-name').textContent = user.name?.split(' ')[0] || 'there';
document.getElementById('theme-btn').addEventListener('click', toggleTheme);

let macrosChart = null;

// Map snake_case API response to camelCase expected by render functions
function adaptVitals(v) {
  return {
    heartRate:   v.heart_rate,
    spo2:        v.spo2,
    temperature: v.temperature,
    humidity:    v.humidity,
    weight:      v.weight,
    steps:       v.steps,
    timestamp:   v.recorded_at,
  };
}

function adaptMeal(m) {
  return {
    id:            m.id,
    timestamp:     m.logged_at,
    imageUrl:      resolveApiUrl(m.image_url) || null,
    totalCalories: m.total_calories,
    detectedFoods: (m.items || []).map(i => ({
      name:        i.food_name,
      portionSize: i.portion_size,
      calories:    i.calories,
      carbs:       i.carbs,
      protein:     i.protein,
      fat:         i.fat,
    })),
  };
}

function renderVitals(v) {
  countUp(document.getElementById('v-hr'),   v.heartRate,   { decimals: 0 });
  countUp(document.getElementById('v-spo2'), v.spo2,        { decimals: 1 });
  countUp(document.getElementById('v-temp'), v.temperature, { decimals: 1 });
  countUp(document.getElementById('v-hum'),  v.humidity,    { decimals: 0 });
  countUp(document.getElementById('v-wt'),   v.weight,      { decimals: 1 });
  countUp(document.getElementById('v-steps'),v.steps,       { decimals: 0 });
  document.getElementById('s-hr').innerHTML   = statusDot(vitalsStatus('heartRate',   v.heartRate));
  document.getElementById('s-spo2').innerHTML = statusDot(vitalsStatus('spo2',        v.spo2));
  document.getElementById('s-temp').innerHTML = statusDot(vitalsStatus('temperature', v.temperature));
  document.getElementById('last-sync').textContent = 'Last synced ' + formatTime(v.timestamp);
}

function renderRec(rec) {
  document.getElementById('rec-text').textContent = rec.message || '';
  const trigger = document.getElementById('rec-trigger');
  if (trigger) trigger.textContent = '';
}

async function renderNutrition(meals, goal) {
  const total  = meals.reduce((s, m) => s + m.totalCalories, 0);
  const macros = meals.flatMap(m => m.detectedFoods).reduce(
    (acc, f) => { acc.carbs += f.carbs || 0; acc.protein += f.protein || 0; acc.fat += f.fat || 0; return acc; },
    { carbs: 0, protein: 0, fat: 0 }
  );

  document.getElementById('cal-goal').textContent  = goal.toLocaleString();
  countUp(document.getElementById('cal-eaten'), total, { decimals: 0 });
  document.getElementById('meal-count').textContent = meals.length;

  const ring  = document.getElementById('cal-ring');
  const circ  = 2 * Math.PI * 52;
  ring.style.strokeDashoffset = String(circ * (1 - Math.min(1, total / goal)));

  const ctx = document.getElementById('macros-chart');
  if (!(await waitForChart())) {
    ctx.parentElement.innerHTML = '<div class="center muted text-sm">Macro chart unavailable.</div>';
    return;
  }
  if (macrosChart) macrosChart.destroy();
  macrosChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Carbs (g)', 'Protein (g)', 'Fat (g)'],
      datasets: [{ data: [macros.carbs, macros.protein, macros.fat], backgroundColor: ['#1B4332', '#00BFA5', '#D97706'], borderWidth: 0 }],
    },
    options: { cutout: '62%', responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { font: { family: 'DM Sans' }, boxWidth: 10 } } }, animation: { duration: 700 } },
  });
}

function renderRecentMeals(meals) {
  const host = document.getElementById('recent-meals');
  if (!meals.length) {
    host.innerHTML = `<div class="card center muted">No meals yet today. <a href="food-log.html">Log your first meal</a></div>`;
    return;
  }
  host.innerHTML = meals.map(m => `
    <div class="list-item">
      ${m.imageUrl ? `<img src="${m.imageUrl}" alt="" class="meal-thumb" loading="lazy" />` : '<div class="meal-thumb" style="background:var(--surface-2)"></div>'}
      <div style="flex:1; min-width:0">
        <div style="font-weight:600">${m.detectedFoods.map(f => f.name).join(', ') || 'Meal'}</div>
        <div class="text-xs muted">${formatTime(m.timestamp)} · ${m.detectedFoods.length} items</div>
      </div>
      <div class="num" style="font-weight:600">${m.totalCalories}<span class="text-xs muted"> kcal</span></div>
    </div>
  `).join('');
}

async function loadAll() {
  // Profile — source of truth for the calorie target and display name.
  // The localStorage cache only ever holds {id, name, email} from login/register,
  // so it never reflects a target the user set later in Profile settings.
  let calorieGoal = user.daily_calorie_target || 2200;
  try {
    const profile = await api.get('/users/profile');
    user = { ...user, ...profile };
    saveUser(user);
    document.getElementById('hello-name').textContent = profile.name?.split(' ')[0] || 'there';
    calorieGoal = profile.daily_calorie_target || 2200;
  } catch { /* fall back to cached/default goal */ }

  // Vitals
  try {
    const v = await api.get('/vitals/latest');
    renderVitals(adaptVitals(v));
  } catch {
    document.getElementById('last-sync').textContent = 'No device data yet';
  }

  // Recommendations
  try {
    const recs = await api.get('/recommendations/');
    if (recs.length) {
      renderRec(recs[0]);
    } else {
      document.getElementById('rec-text').textContent = 'No tips yet — log a meal or sync your device to get personalized recommendations.';
    }
  } catch {
    document.getElementById('rec-text').textContent = 'Could not load your recommendation right now.';
  }

  // Meals (today)
  try {
    const rawMeals = await api.get('/meals/');
    const today = new Date().toISOString().slice(0, 10);
    const todayMeals = rawMeals.filter(m => m.logged_at.slice(0, 10) === today).map(adaptMeal);
    await renderNutrition(todayMeals, calorieGoal);
    renderRecentMeals(todayMeals);
  } catch {
    // Still show the real goal (and an empty ring) even if today's meals failed to load
    await renderNutrition([], calorieGoal);
    document.getElementById('recent-meals').innerHTML = '<div class="card center muted">Could not load meals.</div>';
  }

  initLucide();
}

loadAll();

async function syncNow(btn) {
  const label = btn.querySelector('span') || btn;
  const originalText = label.textContent;
  btn.disabled = true;
  label.textContent = 'Syncing…';
  try {
    await loadAll();
    toast('Device readings refreshed');
  } catch {
    toast('Sync failed — check connection', 'error');
  } finally {
    btn.disabled = false;
    label.textContent = originalText;
  }
}

document.getElementById('sync-btn').addEventListener('click', (e) => syncNow(e.currentTarget));
document.getElementById('sync-btn-2').addEventListener('click', (e) => syncNow(e.currentTarget));

// Poll vitals every 30s
setInterval(async () => {
  try {
    const v = await api.get('/vitals/latest');
    renderVitals(adaptVitals(v));
  } catch { /* ignore */ }
}, 30000);
