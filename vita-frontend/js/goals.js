import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { toast, applyStoredTheme, initThemeToggle, initLucide, todayISO, getLocalTimestampDate } from './utils.js';
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
  const userEnteredWeight = Number(document.getElementById('target_weight')?.value);
  const curWeight = (profile.weight != null && Number(profile.weight) > 0)
    ? Number(profile.weight)
    : (userEnteredWeight > 0 ? userEnteredWeight : null);

  const hasWeight = curWeight != null && curWeight > 0;
  const hasHeight = profile.height != null && Number(profile.height) > 0;
  const height    = hasHeight ? Number(profile.height) : null;
  const hasAge    = profile.age != null && Number(profile.age) > 0;
  const age       = hasAge ? Number(profile.age) : null;

  const rawSex    = (profile.sex || 'male').toLowerCase();
  const isFemale  = rawSex === 'female';
  const sexLabel  = isFemale ? 'female' : 'male';
  const goal      = document.getElementById('goal_type')?.value || profile.goal_type || 'maintenance';
  const activity  = document.getElementById('activity_level')?.value || 'moderate';

  // Activity multipliers
  const actMultipliers = {
    sedentary:   1.2,
    light:       1.375,
    moderate:    1.55,
    very_active: 1.725,
  };
  const multiplier = actMultipliers[activity] || 1.55;

  const actLabel = {
    sedentary:   'sedentary',
    light:       'light',
    moderate:    'moderate',
    very_active: 'very active',
  }[activity] || 'moderate';

  // ── 1. Determine Personalization Tier ──────────────────────────────────────
  const isFullyPersonalized = hasAge && hasWeight && hasHeight;
  const refHeight = isFemale ? 162 : 175; // Standard gender reference height (cm)
  const refWeight = isFemale ? 62 : 75;   // Standard gender reference weight (kg)
  const refAge    = 30;                   // Standard adult reference age

  let tdee = 0;
  let bmr = null;
  let calRationale = '';
  let statusBadge = '';
  let personalizationSummary = '';

  if (isFullyPersonalized) {
    // ── Tier 1: Full Personalization (Mifflin-St Jeor with exact user stats) ──
    bmr = 10 * curWeight + 6.25 * height - 5 * age + (isFemale ? -161 : 5);
    tdee = Math.round(bmr * multiplier);
    calRationale = `Calculated from your exact BMR (~${Math.round(bmr)} kcal) and ${actLabel} activity`;
    statusBadge = `<span class="badge badge-success mb-1">✨ Fully Personalized</span>`;
    personalizationSummary = `Personalized to your profile (Age: ${age}, Weight: ${curWeight} kg, Height: ${height} cm, ${sexLabel}).`;
  } else if (hasWeight) {
    // ── Tier 2A: Weight is known (dominant ~75% BMR factor), Age or Height missing ──
    const effectiveHeight = hasHeight ? height : refHeight;
    const effectiveAge    = hasAge ? age : refAge;
    bmr = 10 * curWeight + 6.25 * effectiveHeight - 5 * effectiveAge + (isFemale ? -161 : 5);
    tdee = Math.round(bmr * multiplier);

    const missingParts = [];
    if (!hasAge) missingParts.push('age');
    if (!hasHeight) missingParts.push('height');

    calRationale = `Calculated from your recorded weight (${curWeight} kg) & ${sexLabel} reference ${missingParts.join(' & ')}`;
    statusBadge = `<span class="badge badge-warning mb-1">⚡ Partially Personalized</span>`;
    personalizationSummary = `Using your actual weight (${curWeight} kg) and standard adult ${sexLabel} references for missing ${missingParts.join(' and ')}.`;
  } else if (hasAge) {
    // ── Tier 2B: Age is known, Weight is missing ──
    let ageFactor = 1.0;
    if (age < 25) ageFactor = 1.04;          // Younger adult metabolic rate
    else if (age > 65) ageFactor = 0.90;     // Senior metabolic decline
    else if (age > 50) ageFactor = 0.95;

    const baseTdee = (isFemale ? 2000 : 2500) * (multiplier / 1.55);
    tdee = Math.round(baseTdee * ageFactor);

    calRationale = `Calibrated to your age (${age}) and standard adult ${sexLabel} guidelines`;
    statusBadge = `<span class="badge badge-warning mb-1">⚡ Partially Personalized</span>`;
    personalizationSummary = `Calibrated to your age (${age}) and ${sexLabel} dietary reference (weight not yet logged).`;
  } else {
    // ── Tier 3: General Gender Fallback (Neither Age nor Weight is set) ──
    const baseTdee = (isFemale ? 2000 : 2500) * (multiplier / 1.55);
    tdee = Math.round(baseTdee);

    calRationale = `Standard adult ${sexLabel} baseline (${isFemale ? '2,000' : '2,500'} kcal maintenance)`;
    statusBadge = `<span class="badge badge-info mb-1">ℹ️ General ${sexLabel.toUpperCase()} Guidelines</span>`;
    personalizationSummary = `Using general adult ${sexLabel} health reference guidelines because age and body measurements are not set.`;
  }

  // ── 2. Goal Adjustments on Calorie Target ────────────────────────────────────
  let targetCal = tdee;
  const floor = isFemale ? 1200 : 1500;

  if (goal === 'weight_loss') {
    targetCal = Math.max(floor, tdee - 500);
    calRationale += ` — 500 kcal deficit (safe floor: ${floor} kcal)`;
  } else if (goal === 'weight_gain') {
    const surplus = isFemale ? 250 : 350;
    targetCal = tdee + surplus;
    calRationale += ` — ${surplus} kcal controlled surplus for lean growth`;
  } else {
    calRationale += ` — balanced maintenance energy`;
  }

  // ── 3. Macronutrients (Protein, Carbs, Fat) ─────────────────────────────────
  let targetProtein;
  let proteinRationale;

  if (hasWeight) {
    let proteinRatio = isFemale ? 1.2 : 1.3;
    if (hasAge && age >= 65) {
      proteinRatio = isFemale ? 1.3 : 1.4; // Sarcopenia prevention in older adults
    }
    if (goal === 'weight_loss') {
      proteinRatio = isFemale ? 1.6 : 1.8;
    } else if (goal === 'weight_gain') {
      proteinRatio = isFemale ? 1.8 : 2.0;
    }
    targetProtein = Math.round(curWeight * proteinRatio);
    proteinRationale = `${proteinRatio}g/kg personalized to your ${curWeight} kg weight`;
  } else {
    // Gender reference standard (WHO / Dietary Guidelines for Americans)
    if (goal === 'weight_loss') {
      targetProtein = isFemale ? 110 : 150;
    } else if (goal === 'weight_gain') {
      targetProtein = isFemale ? 120 : 160;
    } else {
      targetProtein = isFemale ? 95 : 130;
    }
    proteinRationale = `Standard adult ${sexLabel} reference (${targetProtein}g for ${goal.replace('_', ' ')})`;
  }

  let targetCarbs;
  let carbsRationale;
  let targetFat;
  let fatRationale;

  if (goal === 'weight_loss') {
    targetCarbs = Math.round((targetCal * 0.38) / 4);
    carbsRationale = `38% of cals for fat oxidation & energy`;
    const fatPct = isFemale ? 0.28 : 0.25;
    targetFat = Math.round((targetCal * fatPct) / 9);
    fatRationale = `${Math.round(fatPct * 100)}% of cals for ${sexLabel} hormonal balance`;
  } else if (goal === 'weight_gain') {
    targetCarbs = Math.round((targetCal * 0.52) / 4);
    carbsRationale = `52% of cals to fuel glycogen & muscle hypertrophy`;
    const fatPct = isFemale ? 0.26 : 0.24;
    targetFat = Math.round((targetCal * fatPct) / 9);
    fatRationale = `${Math.round(fatPct * 100)}% of cals for anabolic hormone synthesis`;
  } else {
    targetCarbs = Math.round((targetCal * 0.48) / 4);
    carbsRationale = `48% of cals for steady all-day energy`;
    const fatPct = isFemale ? 0.30 : 0.28;
    targetFat = Math.round((targetCal * fatPct) / 9);
    fatRationale = `${Math.round(fatPct * 100)}% of cals for metabolic & cellular health`;
  }

  // ── 4. Target Weight ────────────────────────────────────────────────────────
  let targetWeightRec = curWeight || refWeight;
  let weightRationale = '';

  if (hasHeight) {
    const heightM = height / 100;
    let targetBmi = isFemale ? 22.0 : 23.0;
    if (goal === 'weight_gain') targetBmi = isFemale ? 23.5 : 24.5;

    const idealWeight = Math.round(targetBmi * heightM * heightM * 10) / 10;
    if (goal === 'weight_loss' && hasWeight) {
      targetWeightRec = Math.min(curWeight, idealWeight > 30 ? idealWeight : Math.round(curWeight * 0.9 * 10) / 10);
      weightRationale = `Target BMI ~${targetBmi} for sustainable fat loss`;
    } else if (goal === 'weight_gain' && hasWeight) {
      targetWeightRec = Math.max(curWeight, idealWeight > 30 ? idealWeight : Math.round(curWeight * 1.05 * 10) / 10);
      weightRationale = `Target BMI ~${targetBmi} (+${isFemale ? '4%' : '5%'} progression)`;
    } else {
      targetWeightRec = idealWeight;
      weightRationale = `Ideal healthy BMI ~${targetBmi} for ${height} cm ${sexLabel}`;
    }
  } else if (hasWeight) {
    if (goal === 'weight_loss') {
      targetWeightRec = Math.round(curWeight * 0.9 * 10) / 10;
      weightRationale = `Progressive 10% fat loss milestone from ${curWeight} kg`;
    } else if (goal === 'weight_gain') {
      targetWeightRec = Math.round(curWeight * 1.05 * 10) / 10;
      weightRationale = `Progressive 5% lean mass milestone from ${curWeight} kg`;
    } else {
      targetWeightRec = curWeight;
      weightRationale = `Maintain your current healthy ${curWeight} kg weight`;
    }
  } else {
    targetWeightRec = refWeight;
    weightRationale = `Standard adult ${sexLabel} population reference (~${refWeight} kg)`;
  }

  // ── 5. Daily Steps Target ───────────────────────────────────────────────────
  let targetSteps;
  let stepsRationale;

  if (hasAge && age >= 65) {
    targetSteps = goal === 'weight_loss' ? 8500 : 7500;
    stepsRationale = `Longevity baseline with gentle joint impact for age ${age}`;
  } else if (goal === 'weight_loss') {
    targetSteps = isFemale ? 10000 : 10500;
    stepsRationale = `Elevated NEAT expenditure for fat loss`;
  } else if (goal === 'weight_gain') {
    targetSteps = isFemale ? 7000 : 7500;
    stepsRationale = `Maintains cardiovascular base without burning muscle surplus`;
  } else {
    targetSteps = isFemale ? 8000 : 8500;
    stepsRationale = `Cardiovascular & endurance baseline for ${sexLabel}`;
  }

  if (activity === 'very_active') targetSteps += 1000;
  else if (activity === 'sedentary') targetSteps = Math.max(6000, targetSteps - 1000);

  // ── 6. Daily Sleep Target ───────────────────────────────────────────────────
  let targetSleep;
  let sleepRationale;

  if (hasAge) {
    if (age < 25) {
      targetSleep = 8.5;
      sleepRationale = `Supports cognitive consolidation & neuroplasticity for age ${age}`;
    } else if (age >= 65) {
      targetSleep = 7.5;
      sleepRationale = `Circadian restoration for healthy aging (age ${age})`;
    } else {
      targetSleep = isFemale ? 8.0 : 7.5;
      sleepRationale = `Restores hormonal rhythm & energy for adult ${sexLabel}`;
    }
  } else {
    targetSleep = isFemale ? 8.0 : 7.5;
    sleepRationale = `Standard adult ${sexLabel} restorative sleep baseline`;
  }

  if (goal === 'weight_loss') {
    targetSleep = Math.min(9.0, targetSleep + 0.5);
    sleepRationale += ` (+0.5h for appetite ghrelin regulation)`;
  } else if (goal === 'weight_gain') {
    targetSleep = Math.min(9.0, targetSleep + 0.5);
    sleepRationale += ` (+0.5h for muscle growth hormone recovery)`;
  }

  // ── 7. Daily Water Intake Target ────────────────────────────────────────────
  let targetWater;
  let waterRationale;

  if (hasWeight) {
    const mlPerKg = isFemale ? 0.033 : 0.035;
    const bonus = (goal === 'weight_loss' || activity === 'very_active') ? 0.3 : 0.1;
    targetWater = Number((curWeight * mlPerKg + bonus).toFixed(1));
    waterRationale = `${Math.round(mlPerKg * 1000)}ml/kg personalized to your ${curWeight} kg weight`;
  } else {
    // Institute of Medicine (IOM) adult fluid standard: Men 3.7L, Women 2.7L
    targetWater = isFemale ? 2.7 : 3.7;
    waterRationale = `Institute of Medicine general ${sexLabel} standard (${isFemale ? '2.7L' : '3.7L'})`;
  }

  // ── 8. Assemble smartRecs object ────────────────────────────────────────────
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

  // Render individual per-field chips
  renderFieldChip('rec-chip-calories', 'daily_calorie_target', targetCal, 'Recommended', calRationale);
  renderFieldChip('rec-chip-weight',   'target_weight',        targetWeightRec, 'Target', weightRationale);
  renderFieldChip('rec-chip-protein',  'target_protein',       targetProtein, 'Recommended', proteinRationale);
  renderFieldChip('rec-chip-carbs',    'target_carbs',         targetCarbs, 'Recommended', carbsRationale);
  renderFieldChip('rec-chip-fat',      'target_fat',           targetFat, 'Recommended', fatRationale);
  renderFieldChip('rec-chip-steps',    'target_steps',         targetSteps, 'Recommended', stepsRationale);
  renderFieldChip('rec-chip-sleep',    'target_sleep',         targetSleep, 'Recommended', sleepRationale);
  renderFieldChip('rec-chip-water',    'target_water',         targetWater, 'Recommended', waterRationale);

  // ── 9. Render Smart Assistant Box Description ───────────────────────────────
  const descEl = document.getElementById('smart-calc-desc');
  if (descEl) {
    let promptHtml = '';
    if (!isFullyPersonalized) {
      promptHtml = ` <a href="profile.html" style="color:var(--teal-600); text-decoration:underline; font-weight:600">Update your profile</a> to unlock exact BMR & metabolic calculations.`;
    }

    descEl.innerHTML = `
      <div style="margin-bottom:0.4rem">${statusBadge}</div>
      <div>${personalizationSummary} For your <strong>${goal.replace('_', ' ')}</strong> goal and <strong>${actLabel}</strong> activity: recommended intake is <strong>${targetCal.toLocaleString()} kcal/day</strong> with <strong>${targetProtein}g protein</strong>, <strong>${targetSteps.toLocaleString()} steps</strong>, and <strong>${targetSleep}h sleep</strong>.${promptHtml}</div>
    `;
    if (window.lucide) window.lucide.createIcons();
  }
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
  const consumedCal  = todayMeals.reduce((sum, m) => sum + (m.total_calories || 0), 0);
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

  // 3. Macros (raw API: total_protein, total_carbs, total_fat)
  const loggedProtein = Math.round(todayMeals.reduce((sum, m) => sum + (m.total_protein || 0), 0));
  const loggedCarbs   = Math.round(todayMeals.reduce((sum, m) => sum + (m.total_carbs   || 0), 0));
  const loggedFat     = Math.round(todayMeals.reduce((sum, m) => sum + (m.total_fat     || 0), 0));

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

    // Fetch meals & vitals for today (reset at 12:00 AM local time)
    const today = todayISO();
    try {
      const allMeals = await api.get('/meals/');
      todayMeals = (allMeals || []).filter((m) => getLocalTimestampDate(m.logged_at) === today);
    } catch {
      todayMeals = [];
    }

    try {
      latestVitals = (await api.get('/vitals/latest?date_str=' + today)) || {};
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
    // Persist full profile to localStorage so dashboard reads the correct step target on next boot
    const { getUser, saveUser } = await import('./auth.js');
    saveUser({ ...getUser(), ...profile });
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
