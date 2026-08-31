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
let fieldRecommendations = {};

const setVal = (id, v) => {
  const el = document.getElementById(id);
  if (el) el.value = v ?? '';
};

function applyFieldRecommendation(fieldId, value) {
  const el = document.getElementById(fieldId);
  if (!el || el.disabled) return;
  el.value = value;
  el.classList.remove('field-highlight');
  void el.offsetWidth; // trigger reflow for animation
  el.classList.add('field-highlight');
  toast(`Applied ${value} for ${el.previousElementSibling?.textContent || 'target'}`);
}

function renderFieldChip(chipId, targetInputId, value, label, rationale) {
  const chipEl = document.getElementById(chipId);
  if (!chipEl) return;
  chipEl.innerHTML = `<span>💡 ${label}: <strong>${value}</strong> <span class="muted text-xs">(${rationale})</span></span> <span class="chip-action">Apply →</span>`;
  chipEl.classList.remove('hidden');
  chipEl.onclick = () => applyFieldRecommendation(targetInputId, value);
}

function computeSmartRecommendations() {
  const curWeight = Number(profile.weight || 70);
  const userEnteredWeight = Number(document.getElementById('target_weight')?.value);
  const weight = userEnteredWeight > 0 ? userEnteredWeight : curWeight;
  const height = Number(profile.height || 170);
  const age    = Number(profile.age || 30);
  const sex    = (profile.sex || 'male').toLowerCase();
  const isFemale = sex === 'female';
  const goal   = document.getElementById('goal_type')?.value || profile.goal_type || 'maintenance';
  const activity = document.getElementById('activity_level')?.value || 'moderate';

  // 1. Mifflin-St Jeor BMR
  let bmr = 10 * curWeight + 6.25 * height - 5 * age;
  if (isFemale) {
    bmr -= 161;
  } else {
    bmr += 5;
  }

  // 2. Activity multipliers
  const actMultipliers = {
    sedentary:   1.2,
    light:       1.375,
    moderate:    1.55,
    very_active: 1.725,
  };
  const multiplier = actMultipliers[activity] || 1.55;
  const tdee = Math.round(bmr * multiplier);

  const actLabel = {
    sedentary:   'sedentary',
    light:       'light',
    moderate:    'moderate',
    very_active: 'very active',
  }[activity] || 'moderate';

  const sexLabel = isFemale ? 'female' : 'male';

  // 3. Goal & Sex-specific target calculations
  let targetCal = tdee;
  let calRationale = `Matches ${sexLabel} TDEE for balanced energy`;
  let targetWeightRec = curWeight;
  let weightRationale = `Maintain healthy current weight`;
  let targetProtein = Math.round(curWeight * (isFemale ? 1.2 : 1.3));
  let proteinRationale = `${isFemale ? '1.2' : '1.3'}g/kg for cellular repair`;
  let targetCarbs = Math.round((tdee * 0.48) / 4);
  let carbsRationale = `48% of cals for steady vitality`;
  let targetFat = Math.round((tdee * (isFemale ? 0.30 : 0.28)) / 9);
  let fatRationale = `${isFemale ? '30%' : '28%'} of cals for endocrine health`;
  let targetSteps = isFemale ? 8000 : 8500;
  let stepsRationale = `Cardiovascular & longevity baseline`;
  let targetSleep = isFemale ? 8.0 : 7.5;
  let sleepRationale = `Circadian restoration & mental focus`;
  let targetWater = Number((curWeight * (isFemale ? 0.032 : 0.034)).toFixed(1));
  let waterRationale = `${isFemale ? '32' : '34'}ml/kg fluid equilibrium`;
  let overallRationale = '';

  const heightM = height / 100;
  const targetBmi = isFemale ? 22.0 : 23.0;

  if (goal === 'weight_loss') {
    const floor = isFemale ? 1200 : 1500;
    targetCal = Math.max(floor, tdee - 500);
    calRationale = `TDEE - 500 kcal deficit (safety floor: ${floor} kcal)`;

    const idealWeight = Math.round(targetBmi * heightM * heightM * 10) / 10;
    targetWeightRec = Math.min(curWeight, idealWeight > 30 ? idealWeight : Math.round(curWeight * 0.9 * 10) / 10);
    weightRationale = `Target BMI ~${targetBmi} for sustainable fat loss`;

    const proteinRatio = isFemale ? 1.6 : 1.8;
    targetProtein = Math.round(curWeight * proteinRatio);
    proteinRationale = `${proteinRatio}g/kg preserves lean muscle in deficit`;

    targetCarbs = Math.round((targetCal * 0.38) / 4);
    carbsRationale = `38% of cals for fat oxidation & energy`;

    const fatPct = isFemale ? 0.28 : 0.25;
    targetFat = Math.round((targetCal * fatPct) / 9);
    fatRationale = `${Math.round(fatPct * 100)}% of cals for ${sexLabel} hormonal health`;

    targetSteps = isFemale ? 10000 : 10500;
    stepsRationale = `Elevated NEAT expenditure for fat loss`;

    targetSleep = isFemale ? 8.5 : 8.0;
    sleepRationale = `Regulates ghrelin appetite & lowers cortisol`;

    targetWater = Number((curWeight * (isFemale ? 0.034 : 0.036) + 0.2).toFixed(1));
    waterRationale = `Supports metabolic hydration & appetite control`;

    overallRationale = `Based on your ${sexLabel} BMR (~${Math.round(bmr)} kcal) and <strong>${actLabel}</strong> activity (TDEE ~${tdee} kcal), a safe 500 kcal deficit targets <strong>${targetCal} kcal/day</strong>, <strong>${targetProtein}g protein</strong> for muscle retention, <strong>${targetSteps.toLocaleString()} steps</strong>, and <strong>${targetSleep}h sleep</strong>.`;

  } else if (goal === 'weight_gain') {
    const surplus = isFemale ? 250 : 350;
    targetCal = tdee + surplus;
    calRationale = `TDEE + ${surplus} kcal controlled lean surplus`;

    const gainTargetBmi = isFemale ? 23.5 : 24.5;
    const gainWeight = Math.round(gainTargetBmi * heightM * heightM * 10) / 10;
    targetWeightRec = Math.max(curWeight, gainWeight > 30 ? gainWeight : Math.round(curWeight * 1.05 * 10) / 10);
    weightRationale = `Lean mass target (+${isFemale ? '4%' : '5%'} progression)`;

    const proteinRatio = isFemale ? 1.8 : 2.0;
    targetProtein = Math.round(curWeight * proteinRatio);
    proteinRationale = `${proteinRatio}g/kg maximizes muscle protein synthesis`;

    targetCarbs = Math.round((targetCal * 0.52) / 4);
    carbsRationale = `52% of cals to replenish muscle glycogen`;

    const fatPct = isFemale ? 0.26 : 0.24;
    targetFat = Math.round((targetCal * fatPct) / 9);
    fatRationale = `${Math.round(fatPct * 100)}% of cals for hormone synthesis`;

    targetSteps = isFemale ? 7000 : 7500;
    stepsRationale = `Maintains conditioning without burning muscle fuel`;

    targetSleep = isFemale ? 8.5 : 8.5;
    sleepRationale = `Maximizes Growth Hormone & deep tissue recovery`;

    targetWater = Number((curWeight * (isFemale ? 0.036 : 0.038) + 0.3).toFixed(1));
    waterRationale = `Intramuscular hydration & recovery`;

    overallRationale = `Based on your ${sexLabel} BMR (~${Math.round(bmr)} kcal) and <strong>${actLabel}</strong> activity (TDEE ~${tdee} kcal), a lean ${surplus} kcal surplus targets <strong>${targetCal} kcal/day</strong> with <strong>${targetProtein}g protein</strong> for hypertrophy and <strong>${targetSleep}h sleep</strong> for optimal growth.`;

  } else {
    // General Wellness / Maintenance
    overallRationale = `Based on your ${sexLabel} BMR (~${Math.round(bmr)} kcal) and <strong>${actLabel}</strong> activity (TDEE ~${tdee} kcal), maintaining weight targets <strong>${targetCal} kcal/day</strong>, <strong>${targetProtein}g protein</strong>, and <strong>${targetSteps.toLocaleString()} steps/day</strong> for sustained vitality.`;
  }

  smartRecs = {
    daily_calorie_target: targetCal,
    target_weight:        targetWeightRec,
    target_protein:       targetProtein,
    target_carbs:         targetCarbs,
    target_fat:           targetFat,
    target_steps:         targetSteps,
    target_sleep:         targetSleep,
    target_water:         targetWater,
  };

  // Render individual per-field recommendation chips
  renderFieldChip('rec-chip-calories', 'daily_calorie_target', targetCal, 'Recommended', calRationale);
  renderFieldChip('rec-chip-weight',   'target_weight',        targetWeightRec, 'Target', weightRationale);
  renderFieldChip('rec-chip-protein',  'target_protein',       targetProtein, 'Recommended', proteinRationale);
  renderFieldChip('rec-chip-carbs',    'target_carbs',         targetCarbs, 'Recommended', carbsRationale);
  renderFieldChip('rec-chip-fat',      'target_fat',           targetFat, 'Recommended', fatRationale);
  renderFieldChip('rec-chip-steps',    'target_steps',         targetSteps, 'Recommended', stepsRationale);
  renderFieldChip('rec-chip-sleep',    'target_sleep',         targetSleep, 'Recommended', sleepRationale);
  renderFieldChip('rec-chip-water',    'target_water',         targetWater, 'Recommended', waterRationale);

  const descEl = document.getElementById('smart-calc-desc');
  if (descEl) descEl.innerHTML = overallRationale;
}

function renderMonitoring() {
  const savedTargets = profile.notification_preferences?.targets || {};
  const calTarget     = profile.daily_calorie_target || 2000;
  const stepTarget    = savedTargets.target_steps   || 10000;
  const proteinTarget = savedTargets.target_protein || Math.round((profile.weight || 70) * 1.4);
  const carbsTarget   = savedTargets.target_carbs   || 220;
  const fatTarget     = savedTargets.target_fat     || 60;
  const sleepTarget   = savedTargets.target_sleep   || 8.0;
  const targetWeight  = savedTargets.target_weight  || null;

  // Set today's date label
  const dateEl = document.getElementById('monitor-date');
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  }

  // 1. Calories
  const consumedCal  = todayMeals.reduce((sum, m) => sum + (m.calories || 0), 0);
  const calPct       = Math.min(100, Math.round((consumedCal / calTarget) * 100));
  const calRemaining = Math.max(0, calTarget - consumedCal);
  document.getElementById('cal-consumed').textContent       = Math.round(consumedCal).toLocaleString();
  document.getElementById('cal-target-display').textContent = Math.round(calTarget).toLocaleString();
  document.getElementById('cal-bar').style.width            = `${calPct}%`;
  document.getElementById('cal-status').textContent         = `${calPct}% reached`;
  document.getElementById('cal-remaining').textContent      = `${Math.round(calRemaining).toLocaleString()} kcal remaining`;

  // 2. Steps
  const steps   = latestVitals.steps || 0;
  const stepPct = Math.min(100, Math.round((steps / stepTarget) * 100));
  document.getElementById('steps-logged').textContent         = steps.toLocaleString();
  document.getElementById('steps-target-display').textContent = stepTarget.toLocaleString();
  document.getElementById('steps-bar').style.width            = `${stepPct}%`;
  document.getElementById('steps-percent').textContent        = `${stepPct}% of daily goal`;
  document.getElementById('step-status').textContent          = stepPct >= 100
    ? 'Goal reached! 🎉'
    : `${(stepTarget - steps).toLocaleString()} steps to go`;

  // 3. Macros
  const loggedProtein = Math.round(todayMeals.reduce((sum, m) => sum + (m.protein_g || 0), 0));
  const loggedCarbs   = Math.round(todayMeals.reduce((sum, m) => sum + (m.carbs_g   || 0), 0));
  const loggedFat     = Math.round(todayMeals.reduce((sum, m) => sum + (m.fat_g     || 0), 0));

  document.getElementById('protein-progress').textContent = `${loggedProtein} / ${proteinTarget}g`;
  document.getElementById('protein-bar').style.width      = `${Math.min(100, Math.round((loggedProtein / proteinTarget) * 100))}%`;

  document.getElementById('carbs-progress').textContent   = `${loggedCarbs} / ${carbsTarget}g`;
  document.getElementById('carbs-bar').style.width        = `${Math.min(100, Math.round((loggedCarbs / carbsTarget) * 100))}%`;

  document.getElementById('fat-progress').textContent     = `${loggedFat} / ${fatTarget}g`;
  document.getElementById('fat-bar').style.width          = `${Math.min(100, Math.round((loggedFat / fatTarget) * 100))}%`;

  // 4. Sleep & Weight
  const sleepHours = latestVitals.sleep_duration_min
    ? Number((latestVitals.sleep_duration_min / 60).toFixed(1))
    : 0;
  document.getElementById('sleep-progress').textContent = `${sleepHours} / ${sleepTarget} hrs`;
  document.getElementById('sleep-bar').style.width      = `${Math.min(100, Math.round((sleepHours / sleepTarget) * 100))}%`;

  const curWt = latestVitals.weight || profile.weight;
  document.getElementById('cur-weight').textContent          = curWt ? `${Number(curWt).toFixed(1)} kg` : '—';
  document.getElementById('target-weight-display').textContent = targetWeight
    ? `${Number(targetWeight).toFixed(1)} kg`
    : 'Not set';
}

async function loadAllGoalsData() {
  try {
    profile = await api.get('/users/profile');
    const savedTargets = profile.notification_preferences?.targets || {};

    setVal('goal_type',            profile.goal_type || 'maintenance');
    setVal('activity_level',       savedTargets.activity_level || 'moderate');
    setVal('daily_calorie_target', profile.daily_calorie_target || 2000);
    setVal('target_weight',        savedTargets.target_weight);
    setVal('target_protein',       savedTargets.target_protein || Math.round((profile.weight || 70) * 1.4));
    setVal('target_carbs',         savedTargets.target_carbs   || 220);
    setVal('target_fat',           savedTargets.target_fat     || 60);
    setVal('target_steps',         savedTargets.target_steps   || 10000);
    setVal('target_sleep',         savedTargets.target_sleep   || 8.0);
    setVal('target_water',         savedTargets.target_water   || 2.5);

    computeSmartRecommendations();

    // Fetch meals & vitals for today
    try {
      const allMeals = await api.get('/meals/');
      const today    = new Date().toISOString().slice(0, 10);
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

// ── Edit Mode Logic ───────────────────────────────────────────────────────────
const goalsFields = () =>
  document.querySelectorAll('#goals-page-form input, #goals-page-form select');
let snapshot = {};

function captureSnapshot() {
  goalsFields().forEach((f) => { snapshot[f.id] = f.value; });
}
function restoreSnapshot() {
  goalsFields().forEach((f) => { if (f.id in snapshot) f.value = snapshot[f.id]; });
}

function setGoalsEditMode(editing) {
  const form = document.getElementById('goals-page-form');
  goalsFields().forEach((f) => { f.disabled = !editing; });
  form.classList.toggle('profile-readonly', !editing);
  document.getElementById('edit-goals-btn').classList.toggle('hidden', editing);
  document.getElementById('goals-actions').classList.toggle('hidden', !editing);
  document.getElementById('apply-rec-btn').classList.toggle('hidden', !editing);
  if (editing) initLucide();
}

// If redirected with ?edit=1 (e.g. from Profile page "Edit targets" button)
const urlParams = new URLSearchParams(window.location.search);
const shouldStartInEditMode = urlParams.get('edit') === '1';

setGoalsEditMode(shouldStartInEditMode);

loadAllGoalsData().then(() => {
  if (shouldStartInEditMode) {
    captureSnapshot();
    setGoalsEditMode(true);
    computeSmartRecommendations();
  }
  // Ensure icons render after all content is loaded
  initLucide();
});

// ── Event Listeners ───────────────────────────────────────────────────────────
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
    setVal('target_protein',       smartRecs.target_protein);
    setVal('target_carbs',         smartRecs.target_carbs);
    setVal('target_fat',           smartRecs.target_fat);
    setVal('target_steps',         smartRecs.target_steps);
    setVal('target_sleep',         smartRecs.target_sleep);
    setVal('target_water',         smartRecs.target_water);
    toast('Applied all recommended targets!');
  }
});

document.getElementById('goals-page-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const get = (id) => document.getElementById(id)?.value ?? '';
  const btn = e.submitter || document.querySelector('#goals-actions button[type="submit"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

  try {
    const existingNotif = profile.notification_preferences || {};
    const targets = {
      activity_level: get('activity_level') || 'moderate',
      target_weight:  Number(get('target_weight'))  || undefined,
      target_protein: Number(get('target_protein')) || undefined,
      target_carbs:   Number(get('target_carbs'))   || undefined,
      target_fat:     Number(get('target_fat'))      || undefined,
      target_steps:   Number(get('target_steps'))   || undefined,
      target_sleep:   Number(get('target_sleep'))   || undefined,
      target_water:   Number(get('target_water'))   || undefined,
    };

    const payload = {
      goal_type:             get('goal_type') || undefined,
      daily_calorie_target:  Number(get('daily_calorie_target')) || undefined,
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
    if (btn) { btn.disabled = false; btn.textContent = 'Save targets'; }
  }
});
