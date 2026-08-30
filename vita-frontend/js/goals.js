import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { toast, applyStoredTheme, initThemeToggle, initLucide } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('goals.html');
initThemeToggle();

let profile = {};
let todayMeals = [];
let latestVitals = {};
let smartRecs = {};

const setVal = (id, v) => {
  const el = document.getElementById(id);
  if (el) el.value = v ?? '';
};

function computeSmartRecommendations() {
  const weight = Number(document.getElementById('target_weight')?.value || profile.weight || 70);
  const height = Number(profile.height || 170);
  const age = Number(profile.age || 30);
  const sex = (profile.sex || 'male').toLowerCase();
  const goal = document.getElementById('goal_type')?.value || profile.goal_type || 'maintenance';
  const activity = document.getElementById('activity_level')?.value || 'moderate';

  // Mifflin-St Jeor BMR
  let bmr = 10 * weight + 6.25 * height - 5 * age;
  if (sex === 'female') {
    bmr -= 161;
  } else {
    bmr += 5;
  }

  // Activity multipliers
  const actMultipliers = {
    sedentary: 1.2,
    light: 1.375,
    moderate: 1.55,
    very_active: 1.725,
  };
  const multiplier = actMultipliers[activity] || 1.55;
  const tdee = Math.round(bmr * multiplier);

  let targetCal = tdee;
  let targetProtein = Math.round(weight * 1.3);
  let targetCarbs = Math.round((tdee * 0.45) / 4);
  let targetFat = Math.round((tdee * 0.30) / 9);
  let targetSteps = 9000;
  let targetSleep = 8.0;
  let targetWater = Number((weight * 0.033).toFixed(1));
  let rationale = '';

  if (goal === 'weight_loss') {
    const floor = sex === 'female' ? 1200 : 1500;
    targetCal = Math.max(floor, tdee - 500);
    targetProtein = Math.round(weight * 1.7);
    targetCarbs = Math.round((targetCal * 0.40) / 4);
    targetFat = Math.round((targetCal * 0.25) / 9);
    targetSteps = 10000;
    targetSleep = 8.0;
    targetWater = Number((weight * 0.035).toFixed(1));
    rationale = Based on your BMR (~ kcal) and <strong></strong> activity (TDEE ~ kcal), a safe 500 kcal deficit targets <strong> kcal/day</strong>, <strong>g protein</strong> for muscle preservation, <strong> steps</strong>, and <strong>L hydration</strong>.;
  } else if (goal === 'weight_gain') {
    targetCal = tdee + 300;
    targetProtein = Math.round(weight * 1.9);
    targetCarbs = Math.round((targetCal * 0.50) / 4);
    targetFat = Math.round((targetCal * 0.25) / 9);
    targetSteps = 8000;
    targetSleep = 8.5;
    targetWater = Number((weight * 0.038).toFixed(1));
    rationale = Based on your BMR (~ kcal) and <strong></strong> activity (TDEE ~ kcal), a lean 300 kcal surplus targets <strong> kcal/day</strong> with <strong>g protein</strong> for hypertrophy and <strong>h sleep</strong> for optimal recovery.;
  } else {
    rationale = Based on your BMR (~ kcal) and <strong></strong> activity (TDEE ~ kcal), maintaining weight targets <strong> kcal/day</strong>, <strong>g protein</strong>, and <strong> steps/day</strong> for sustained health.;
  }

  smartRecs = {
    daily_calorie_target: targetCal,
    target_protein: targetProtein,
    target_carbs: targetCarbs,
    target_fat: targetFat,
    target_steps: targetSteps,
    target_sleep: targetSleep,
    target_water: targetWater,
  };

  const descEl = document.getElementById('smart-calc-desc');
  if (descEl) descEl.innerHTML = rationale;
}

function renderMonitoring() {
  const savedTargets = profile.notification_preferences?.targets || {};
  const calTarget = profile.daily_calorie_target || 2000;
  const stepTarget = savedTargets.target_steps || 10000;
  const proteinTarget = savedTargets.target_protein || Math.round((profile.weight || 70) * 1.4);
  const carbsTarget = savedTargets.target_carbs || 220;
  const fatTarget = savedTargets.target_fat || 60;
  const sleepTarget = savedTargets.target_sleep || 8.0;
  const targetWeight = savedTargets.target_weight || '—';

  // 1. Calories
  const consumedCal = todayMeals.reduce((sum, m) => sum + (m.calories || 0), 0);
  const calPct = Math.min(100, Math.round((consumedCal / calTarget) * 100));
  const calRemaining = Math.max(0, calTarget - consumedCal);
  document.getElementById('cal-consumed').textContent = Math.round(consumedCal).toLocaleString();
  document.getElementById('cal-target-display').textContent = Math.round(calTarget).toLocaleString();
  document.getElementById('cal-bar').style.width = ${calPct}%;
  document.getElementById('cal-status').textContent = ${calPct}% reached;
  document.getElementById('cal-remaining').textContent = ${Math.round(calRemaining).toLocaleString()} kcal remaining;

  // 2. Steps
  const steps = latestVitals.steps || 0;
  const stepPct = Math.min(100, Math.round((steps / stepTarget) * 100));
  document.getElementById('steps-logged').textContent = steps.toLocaleString();
  document.getElementById('steps-target-display').textContent = stepTarget.toLocaleString();
  document.getElementById('steps-bar').style.width = ${stepPct}%;
  document.getElementById('steps-percent').textContent = ${stepPct}% of daily goal;
  document.getElementById('step-status').textContent = stepPct >= 100 ? 'Goal reached!' : ${(stepTarget - steps).toLocaleString()} steps to go;

  // 3. Macros
  const loggedProtein = Math.round(todayMeals.reduce((sum, m) => sum + (m.protein_g || 0), 0));
  const loggedCarbs = Math.round(todayMeals.reduce((sum, m) => sum + (m.carbs_g || 0), 0));
  const loggedFat = Math.round(todayMeals.reduce((sum, m) => sum + (m.fat_g || 0), 0));

  document.getElementById('protein-progress').textContent = ${loggedProtein} / g;
  document.getElementById('protein-bar').style.width = ${Math.min(100, Math.round((loggedProtein / proteinTarget) * 100))}%;

  document.getElementById('carbs-progress').textContent = ${loggedCarbs} / g;
  document.getElementById('carbs-bar').style.width = ${Math.min(100, Math.round((loggedCarbs / carbsTarget) * 100))}%;

  document.getElementById('fat-progress').textContent = ${loggedFat} / g;
  document.getElementById('fat-bar').style.width = ${Math.min(100, Math.round((loggedFat / fatTarget) * 100))}%;

  // 4. Sleep & Weight
  const sleepHours = latestVitals.sleep_duration_min ? Number((latestVitals.sleep_duration_min / 60).toFixed(1)) : 0;
  document.getElementById('sleep-progress').textContent = ${sleepHours} /  hrs;
  document.getElementById('sleep-bar').style.width = ${Math.min(100, Math.round((sleepHours / sleepTarget) * 100))}%;

  const curWt = latestVitals.weight || profile.weight;
  document.getElementById('cur-weight').textContent = curWt ? ${curWt.toFixed(1)} kg : '—';
  document.getElementById('target-weight-display').textContent = targetWeight !== '—' ? ${Number(targetWeight).toFixed(1)} kg : 'Not set';
}

async function loadAllGoalsData() {
  try {
    profile = await api.get('/users/profile');
    const savedTargets = profile.notification_preferences?.targets || {};

    setVal('goal_type', profile.goal_type || 'maintenance');
    setVal('activity_level', savedTargets.activity_level || 'moderate');
    setVal('daily_calorie_target', profile.daily_calorie_target || 2000);
    setVal('target_weight', savedTargets.target_weight);
    setVal('target_protein', savedTargets.target_protein || Math.round((profile.weight || 70) * 1.4));
    setVal('target_carbs', savedTargets.target_carbs || 220);
    setVal('target_fat', savedTargets.target_fat || 60);
    setVal('target_steps', savedTargets.target_steps || 10000);
    setVal('target_sleep', savedTargets.target_sleep || 8.0);
    setVal('target_water', savedTargets.target_water || 2.5);

    computeSmartRecommendations();

    // Fetch meals & vitals for today
    try {
      const allMeals = await api.get('/meals/');
      const today = new Date().toISOString().slice(0, 10);
      todayMeals = (allMeals || []).filter((m) => (m.logged_at || '').slice(0, 10) === today);
    } catch {
      todayMeals = [];
    }

    try {
      latestVitals = (await api.get('/vitals/latest')) || {};
    } catch {
      latestVitals = {};
    }

    renderMonitoring();
  } catch (err) {
    toast('Could not load goals data: ' + err.message, 'error');
  }
}

// Edit Mode Logic
const goalsFields = () => document.querySelectorAll('#goals-page-form input, #goals-page-form select');
let snapshot = {};

function captureSnapshot() {
  goalsFields().forEach((f) => {
    snapshot[f.id] = f.value;
  });
}
function restoreSnapshot() {
  goalsFields().forEach((f) => {
    if (f.id in snapshot) f.value = snapshot[f.id];
  });
}

function setGoalsEditMode(editing) {
  const form = document.getElementById('goals-page-form');
  goalsFields().forEach((f) => {
    f.disabled = !editing;
  });
  form.classList.toggle('profile-readonly', !editing);
  document.getElementById('edit-goals-btn').classList.toggle('hidden', editing);
  document.getElementById('goals-actions').classList.toggle('hidden', !editing);
  document.getElementById('apply-rec-btn').classList.toggle('hidden', !editing);
  if (editing) initLucide();
}

setGoalsEditMode(false);
loadAllGoalsData();

document.getElementById('edit-goals-btn').addEventListener('click', () => {
  captureSnapshot();
  setGoalsEditMode(true);
  computeSmartRecommendations();
});

document.getElementById('cancel-goals-btn').addEventListener('click', () => {
  restoreSnapshot();
  setGoalsEditMode(false);
  computeSmartRecommendations();
});

document.getElementById('goal_type').addEventListener('change', computeSmartRecommendations);
document.getElementById('activity_level').addEventListener('change', computeSmartRecommendations);
document.getElementById('target_weight').addEventListener('input', computeSmartRecommendations);

document.getElementById('apply-rec-btn').addEventListener('click', () => {
  if (smartRecs.daily_calorie_target) {
    setVal('daily_calorie_target', smartRecs.daily_calorie_target);
    setVal('target_protein', smartRecs.target_protein);
    setVal('target_carbs', smartRecs.target_carbs);
    setVal('target_fat', smartRecs.target_fat);
    setVal('target_steps', smartRecs.target_steps);
    setVal('target_sleep', smartRecs.target_sleep);
    setVal('target_water', smartRecs.target_water);
    toast('Applied all recommended targets!');
  }
});

document.getElementById('goals-page-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const get = (id) => document.getElementById(id)?.value ?? '';
  const btn = e.submitter || document.querySelector('#goals-actions button[type="submit"]');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Saving…';
  }
  try {
    const existingNotif = profile.notification_preferences || {};
    const targets = {
      activity_level: get('activity_level') || 'moderate',
      target_weight: Number(get('target_weight')) || undefined,
      target_protein: Number(get('target_protein')) || undefined,
      target_carbs: Number(get('target_carbs')) || undefined,
      target_fat: Number(get('target_fat')) || undefined,
      target_steps: Number(get('target_steps')) || undefined,
      target_sleep: Number(get('target_sleep')) || undefined,
      target_water: Number(get('target_water')) || undefined,
    };

    const payload = {
      goal_type: get('goal_type') || undefined,
      daily_calorie_target: Number(get('daily_calorie_target')) || undefined,
      notification_preferences: {
        ...existingNotif,
        targets,
      },
    };

    profile = await api.put('/users/profile', payload);
    setGoalsEditMode(false);
    renderMonitoring();
    computeSmartRecommendations();
    toast('Goals and targets saved!');
  } catch (err) {
    toast('Could not save targets: ' + err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Save targets';
    }
  }
});
