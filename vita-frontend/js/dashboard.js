import { requireAuth, getUser, saveUser } from './auth.js';
import { renderNav } from './nav.js';
import { countUp, vitalsStatus, statusDot, formatTime, formatSleepDuration, toast, applyStoredTheme, initThemeToggle, setSyncingState, initLucide, waitForChart, computeBmi, bmiStatus, todayISO, getLocalTimestampDate } from './utils.js';
import { api, resolveApiUrl } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('dashboard.html');
initThemeToggle();

let user = getUser();
renderDynamicGreeting(user.name?.split(' ')[0] || 'there');

// Immediately render initial contextual card so morning tips are visible without waiting for network calls
try {
  const bootStepsGoal = user.notification_preferences?.targets?.target_steps || user.target_steps;
  const bootGoalEl = document.getElementById('steps-goal-label');
  if (bootGoalEl && bootStepsGoal) {
    bootGoalEl.textContent = `Goal: ${Number(bootStepsGoal).toLocaleString()}`;
  }

  const initialCard = getContextualFallback(user.name?.split(' ')[0] || 'there');
  if (initialCard) {
    renderRec(initialCard);
  }
} catch { /* ignore */ }

let macrosChart = null;
let _lastMeals = []; // cache latest today's meals for the 30s poll
let _lastVitals = null;


// Map snake_case API response to camelCase expected by render functions
function adaptVitals(v) {
  return {
    heartRate:        v.heart_rate,
    spo2:             v.spo2,
    sleepScore:       v.sleep_score,
    sleepDurationMin: v.sleep_duration_min,
    sleepDate:        v.sleep_date,
    caloriesBurned:   v.calories_burned,
    weight:           v.weight,
    steps:            v.steps,
    distanceKm:       v.distance_km,
    timestamp:        v.recorded_at,
    lastGoogleSync:   v.last_google_sync,
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
  const safeCountUp = (id, val, dec = 0) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (val == null || Number.isNaN(val)) {
      el.textContent = '—';
    } else {
      countUp(el, val, { decimals: dec });
    }
  };

  safeCountUp('v-hr',          v.heartRate, 0);
  safeCountUp('v-spo2',        v.spo2, 1);
  safeCountUp('v-sleep-score', v.sleepScore, 0);
  safeCountUp('v-cal-burned',  v.caloriesBurned ?? 0, 0);
  safeCountUp('v-steps',       v.steps ?? 0, 0);
  safeCountUp('v-dist',        v.distanceKm ?? 0, 1);
  safeCountUp('v-wt',          v.weight, 1);

  document.getElementById('s-hr').innerHTML   = statusDot(vitalsStatus('heartRate',   v.heartRate));
  document.getElementById('s-spo2').innerHTML = statusDot(vitalsStatus('spo2',        v.spo2));
  
  const sleepEl = document.getElementById('s-sleep-score');
  if (sleepEl) {
    if (v.sleepScore != null) {
      const durStr = formatSleepDuration(v.sleepDurationMin);
      const status = vitalsStatus('sleepScore', v.sleepScore);
      const label = v.sleepScore >= 85 ? 'Excellent' : v.sleepScore >= 75 ? 'Good' : v.sleepScore >= 60 ? 'Fair' : 'Short / Poor';
      sleepEl.innerHTML = statusDot(status, durStr ? `${durStr} · ${label}` : label);
    } else {
      sleepEl.innerHTML = '<span class="text-xs muted">No sleep logged</span>';
    }
  }
  
  const syncTime = v.lastGoogleSync || v.timestamp;
  document.getElementById('last-sync').textContent = syncTime ? 'Last synced ' + formatTime(syncTime) : 'No sync data yet';
}

function renderBmi(weightKg, heightCm) {
  const bmiEl = document.getElementById('v-bmi');
  const statusEl = document.getElementById('s-bmi');
  const bmi = computeBmi(weightKg, heightCm);
  if (bmi == null) {
    bmiEl.textContent = '—';
    statusEl.innerHTML = `<span class="text-xs muted">${heightCm ? 'No weight reading yet' : 'Add your height in Profile'}</span>`;
    return;
  }
  countUp(bmiEl, bmi, { decimals: 1 });
  const { status, label } = bmiStatus(bmi);
  statusEl.innerHTML = statusDot(status, label);
}

// Dynamic time-of-day greeting
function renderDynamicGreeting(name) {
  const hour = new Date().getHours();
  let greeting = 'Good day';
  if (hour >= 5 && hour < 12) {
    greeting = 'Good morning';
  } else if (hour >= 12 && hour < 18) {
    greeting = 'Good afternoon';
  } else if (hour >= 18 && hour < 21) {
    greeting = 'Good evening';
  } else {
    greeting = 'Good night';
  }
  const greetingEl = document.getElementById('greeting-text');
  if (greetingEl) greetingEl.textContent = greeting;
  const nameEl = document.getElementById('hello-name');
  if (nameEl) nameEl.textContent = name || 'there';
}

const MORNING_WRITEUPS = [
  "A fresh dawn brings new momentum, {name}! Nourish your body with intention, welcome movement with every step, and let’s make today vibrant. Don't forget to log your breakfast!",
  "Rise and thrive, {name}! Today’s vitality is crafted note-by-note—from a glass of water to your first morning walk. Step into the day with clarity and purpose.",
  "Every sunrise is an invitation to feel your best. Fuel up with a balanced morning meal, take a deep breath, and let’s conquer your health targets today.",
  "Good morning, {name}! Your health is built one mindful choice at a time. Let’s start strong today with wholesome nutrition and energizing morning movement.",
  "A brand new day is here to support your growth. Listen to your body, celebrate every step, and nourish yourself with foods that energize your mind.",
  "Morning light is your body’s cue to thrive. Hydrate, take in the fresh air, and log your breakfast to set a steady metabolic rhythm for the day ahead.",
  "Good morning, {name}! Great journeys are forged by small, consistent moments. Make today count by staying active and fueling your body with wholesome goodness.",
  "Rise with the sun, {name}! Let’s channel today’s energy toward your personal goals. Take a brisk walk, savor your meals, and keep your vitality soaring.",
  "A peaceful morning leads to an empowered day. Dedicate today to self-care, balanced nutrition, and joyful movement with every stride.",
  "Good morning, {name}! Yesterday is behind us, and today is brimming with possibilities. Nourish your body, stay hydrated, and embrace today’s movement.",
  "Rise and shine, {name}! Consistency is your superpower. Let’s fuel your metabolism early and lay the foundation for a vibrant, productive day.",
  "Dawn brings fresh vigor. Honor your body today with nutrient-dense foods, mindful breaths, and active steps toward your ultimate wellness.",
  "Good morning, {name}! Step into the daylight with confidence. Log your morning meal, drink your first glass of water, and let’s make today extraordinary.",
  "Every new morning is an opportunity to revitalize your health. Let’s move with joy, eat with awareness, and stay connected with your daily goals."
];

function getRotatingMorningInsight(name) {
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 0);
  const diff = now - startOfYear;
  const dayOfYear = Math.floor(diff / (1000 * 60 * 60 * 24));
  
  // 14-day permutation ensures no repetition twice within a 7-day period
  const idx = Math.abs(dayOfYear) % MORNING_WRITEUPS.length;
  const text = MORNING_WRITEUPS[idx].replace(/{name}/g, name || 'there');
  return {
    badge: 'Morning Vitality ☀️',
    title: 'A Fresh Dawn for Your Wellness',
    message: text,
    action_data: { action_label: 'Log Breakfast', route: 'food-log.html' },
    rule_id: 'dynamic.morning_poetic',
  };
}

// Persist the Good Morning insight once per calendar day using a localStorage guard.
// This ensures it fires at the first page load after midnight (12:00 AM), not every login.
async function checkAndPersistMorningInsight(firstName) {
  const key = `vita_morning_${todayISO()}`;
  if (localStorage.getItem(key)) return; // already persisted today
  localStorage.setItem(key, '1'); // Lock immediately to prevent duplicate concurrent triggers
  const morningCard = getRotatingMorningInsight(firstName);
  await persistContextualInsight(morningCard);
  localStorage.setItem('vita_targets_cleared', '1'); // Any new insight permanently retires onboarding
}

function getRecBadge(rec) {
  if (rec.badge) return rec.badge;
  const isCritical = rec.tier === 'safety' || rec.priority === 'critical' || rec.severity === 'critical';
  if (isCritical) return 'Health Alert 🚨';
  if (rec.rule_id === 'lifestyle.set_daily_targets') return 'Getting Started 🚀';
  if (rec.rule_id === 'dynamic.morning_poetic') return 'Morning Vitality ☀️';
  if (rec.rule_id === 'time.midday_meal_prompt') return 'Fuel Check-In 🥗';
  if (rec.rule_id === 'milestone.meals_logged_on_track') return 'Nutrition On Track 🥗';
  if (rec.rule_id === 'milestone.calories_met') return 'Energy Balance 🎯';
  if (rec.rule_id === 'milestone.steps_met') return 'Milestone Achieved ⭐';
  if (rec.rule_id === 'time.evening_steps_push') return 'Evening Boost 🚶‍♂️';
  if (rec.rule_id === 'time.evening_calorie_push') return 'Calorie Goal 🌙';
  if (rec.type === 'activity') return 'Activity Boost 👟';
  if (rec.type === 'nutrition') return 'Nutrition Tip 🥗';
  if (rec.type === 'health_alert') return 'Wellness Alert ⚠️';
  return "Today's tip";
}

function renderRec(rec) {
  // Remove any legacy tab toggle bar
  const oldSwitcher = document.getElementById('rec-switcher-controls');
  if (oldSwitcher) oldSwitcher.remove();

  if (!rec) {
    renderRecFallback();
    return;
  }

  const textEl = document.getElementById('rec-text');
  const triggerEl = document.getElementById('rec-trigger');
  const badgeEl = document.getElementById('rec-badge');
  if (!textEl) return;

  const isCritical = rec.tier === 'safety' || rec.priority === 'critical' || rec.severity === 'critical';
  const badgeText = getRecBadge(rec);

  if (badgeEl) {
    badgeEl.innerHTML = `<i data-lucide="${isCritical ? 'alert-triangle' : 'sparkles'}"></i> ${badgeText}`;
    if (isCritical) {
      badgeEl.style.background = 'rgba(229, 62, 62, 0.2)';
      badgeEl.style.color = '#ff8080';
      badgeEl.style.borderColor = 'rgba(229, 62, 62, 0.4)';
    } else {
      badgeEl.style.background = '';
      badgeEl.style.color = '';
      badgeEl.style.borderColor = '';
    }
  }

  const titleHtml = rec.title ? `<strong style="display:block; margin-bottom:0.25rem; font-size:1.05rem">${rec.title}</strong>` : '';
  textEl.innerHTML = `${titleHtml}<span>${rec.message || ''}</span>`;

  if (triggerEl) {
    let actionBtn = '';
    const rawRoute = rec.action_data?.route || '';
    const cleanRoute = rawRoute.replace(/^\//, '');
    if (cleanRoute) {
      actionBtn = `<a href="${cleanRoute}" style="background:#ffffff; color:#1B4332; font-weight:700; padding:0.35rem 0.85rem; border-radius:999px; text-decoration:none; display:inline-flex; align-items:center; gap:0.35rem; font-size:0.8125rem; box-shadow:0 2px 8px rgba(0,0,0,0.18);">${rec.action_data?.action_label || 'View Details'} →</a>`;
    }
    const viewAllLink = `<a href="recommendations.html" style="color:rgba(255,255,255,0.9); font-size:0.8125rem; text-decoration:underline; font-weight:500">All insights</a>`;
    triggerEl.innerHTML = `<div class="row between align-center mt-2">${actionBtn || '<span></span>'}${viewAllLink}</div>`;
  }
  initLucide();
}

function getContextualFallback(firstName) {
  const isCleared = localStorage.getItem('vita_targets_cleared') === '1' || (user && user.daily_calorie_target);
  if (!isCleared) {
    return {
      badge: 'Getting Started 🚀',
      title: 'Set Your Daily Health Targets',
      message: 'Personalize your daily calorie, macro, step, and sleep targets to start tracking your progress and receive tailored AI health insights.',
      action_data: { action_label: 'Configure Targets', route: 'goals.html?edit=1' },
      rule_id: 'lifestyle.set_daily_targets',
    };
  }
  return getRotatingMorningInsight(firstName);
}

function renderRecFallback() {
  const firstName = user?.name?.split(' ')[0] || 'there';
  renderRec(getContextualFallback(firstName));
}

// Persist the 3 core daily insights into the database as the day progresses
async function checkAndPersistDailyInsights({ userProfile, userName, vitalsData, mealsData, calorieTarget }) {
  const now = new Date();
  const hour = now.getHours();
  const firstName = userName || userProfile?.name?.split(' ')[0] || 'there';
  const today = todayISO();

  // 1. Morning Insight (Always persisted once per calendar day)
  await checkAndPersistMorningInsight(firstName).catch(() => {});

  // 2a. Calorie Target Celebration — fires immediately whenever target is reached
  const mealsCount = (mealsData || []).length;
  const consumedCals = Math.round((mealsData || []).reduce((sum, m) => sum + (m.totalCalories || 0), 0));
  const calorieMet = calorieTarget > 0 && consumedCals >= calorieTarget;
  const calCrushedKey = `vita_cal_${today}_crushed`;
  if (calorieMet && !localStorage.getItem(calCrushedKey)) {
    localStorage.setItem(calCrushedKey, '1');
    const calCard = {
      badge: 'Energy Balance 🎯',
      title: 'Calorie Target Crushed! 🎉',
      message: `You did it, ${firstName}! You've reached your daily calorie target (${consumedCals.toLocaleString()} / ${calorieTarget.toLocaleString()} kcal). Keep fuelling your body well — great nutrition is the foundation of great health!`,
      action_data: { action_label: 'View Nutrition', route: 'food-log.html' },
      rule_id: 'milestone.calories_met',
      tier: 'primary_action',
    };
    await persistContextualInsight(calCard).catch(() => {});
    localStorage.setItem('vita_targets_cleared', '1');
  }

  // 2b. Midday no-meal prompt — only fires if past noon AND meals are definitely loaded AND strictly 0 meals logged
  if (Array.isArray(mealsData) && mealsData.length === 0 && hour >= 12) {
    const midnoonKey = `vita_meal_${today}_prompt`;
    if (!localStorage.getItem(midnoonKey)) {
      localStorage.setItem(midnoonKey, '1'); // Lock IMMEDIATELY to prevent duplicate concurrent triggers
      const mealCard = {
        badge: 'Fuel Check-In 🥗',
        title: 'Midday Fuel Check-In',
        message: `It's past noon and no meals are logged yet, ${firstName}. If you aren't fasting, take a moment to nourish your body and snap a photo of your lunch to keep your energy steady.`,
        action_data: { action_label: 'Log Lunch', route: 'food-log.html' },
        rule_id: 'time.midday_meal_prompt',
        tier: 'primary_action',
      };
      await persistContextualInsight(mealCard).catch(() => {});
      localStorage.setItem('vita_targets_cleared', '1');
    }
  }

  // 3. Step Goal & Evening Boost
  const savedTargets = userProfile?.notification_preferences?.targets || {};
  const targetSteps = savedTargets.target_steps || userProfile?.target_steps || 10000;
  const steps = vitalsData?.steps || 0;
  const isStepCompleted = targetSteps > 0 && steps >= targetSteps;

  if (isStepCompleted) {
    const stepCrushedKey = `vita_step_${today}_crushed`;
    if (!localStorage.getItem(stepCrushedKey)) {
      localStorage.setItem(stepCrushedKey, '1');
      const stepCard = {
        badge: 'Milestone Achieved ⭐',
        title: 'Daily Step Goal Crushed! 🎉',
        message: `Incredible work, ${firstName}! You've hit ${steps.toLocaleString()} steps, surpassing your daily target of ${targetSteps.toLocaleString()}. Consistent movement powers cardiovascular endurance and metabolic vitality.`,
        action_data: { action_label: 'View Activity', route: 'vitals.html' },
        rule_id: 'milestone.steps_met',
        tier: 'primary_action',
      };
      await persistContextualInsight(stepCard).catch(() => {});
      localStorage.setItem('vita_targets_cleared', '1');
    }
  } else if (hour >= 18) {
    const stepPushKey = `vita_step_${today}_push`;
    if (!localStorage.getItem(stepPushKey)) {
      localStorage.setItem(stepPushKey, '1');
      const remaining = Math.max(0, targetSteps - steps);
      const stepCard = {
        badge: 'Evening Boost 🚶‍♂️',
        title: 'Evening Step Boost',
        message: `You're at ${steps.toLocaleString()} steps—just ${remaining.toLocaleString()} steps away from reaching your daily target of ${targetSteps.toLocaleString()}! A pleasant evening stroll after dinner will carry you across the finish line.`,
        action_data: { action_label: 'Track Activity', route: 'vitals.html' },
        rule_id: 'time.evening_steps_push',
        tier: 'primary_action',
      };
      await persistContextualInsight(stepCard).catch(() => {});
      localStorage.setItem('vita_targets_cleared', '1');
    }
  }
}




async function renderNutrition(meals, goal) {
  const safeGoal = (goal && goal > 0) ? goal : 2200;
  const safeMeals = Array.isArray(meals) ? meals : [];
  const total  = safeMeals.reduce((s, m) => s + (m.totalCalories || 0), 0);
  const macros = safeMeals.flatMap(m => m.detectedFoods || []).reduce(
    (acc, f) => { acc.carbs += f.carbs || 0; acc.protein += f.protein || 0; acc.fat += f.fat || 0; return acc; },
    { carbs: 0, protein: 0, fat: 0 }
  );

  const calGoalEl = document.getElementById('cal-goal');
  if (calGoalEl) calGoalEl.textContent = safeGoal.toLocaleString();

  const calEatenEl = document.getElementById('cal-eaten');
  if (calEatenEl) countUp(calEatenEl, total, { decimals: 0 });

  const mealCountEl = document.getElementById('meal-count');
  if (mealCountEl) mealCountEl.textContent = safeMeals.length;

  const ring  = document.getElementById('cal-ring');
  if (ring) {
    const circ  = 2 * Math.PI * 52;
    ring.style.strokeDashoffset = String(circ * (1 - Math.min(1, total / safeGoal)));
  }

  const ctx = document.getElementById('macros-chart');
  if (!ctx) return;
  if (!(await waitForChart())) {
    if (ctx.parentElement) {
      ctx.parentElement.innerHTML = '<div class="center muted text-sm">Macro chart unavailable.</div>';
    }
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

async function persistContextualInsight(card) {
  if (!card || !card.rule_id) return;
  if (card.id) return; // already in DB

  let type = 'nutrition';
  if (
    card.rule_id.startsWith('activity.') ||
    card.rule_id.startsWith('time.morning_low_steps') ||
    card.rule_id.startsWith('time.evening_steps') ||
    card.rule_id === 'milestone.steps_met'
  ) {
    type = 'activity';
  } else if (
    card.rule_id.startsWith('safety.') ||
    card.rule_id.startsWith('sleep.') ||
    card.rule_id.startsWith('vitals.') ||
    card.rule_id === 'time.morning_low_steps_sleep'
  ) {
    type = 'health_alert';
  } else if (
    card.rule_id.startsWith('goal.') ||
    card.rule_id.startsWith('lifestyle.') ||
    card.rule_id.startsWith('milestone.') ||
    card.rule_id === 'dynamic.morning_poetic'
  ) {
    type = 'goal_progress';
  }

  const payload = {
    type,
    severity: (card.tier === 'safety' || card.priority === 'critical' || card.severity === 'critical') ? 'critical' : 'info',
    tier: card.tier || 'primary_action',
    rule_id: card.rule_id,
    title: card.title || "Today's Insight",
    message: card.message,
    action_data: card.action_data || {},
  };

  try {
    const saved = await api.post('/recommendations/', payload);
    if (saved && saved.id) {
      card.id = saved.id;
    }
  } catch {
    // Non-blocking
  }
}

async function loadAll() {
  let calorieGoal = user.daily_calorie_target || 2200;
  let userName = user.name?.split(' ')[0] || 'there';
  renderDynamicGreeting(userName);

  try {
    const profile = await api.get('/users/profile');
    user = { ...user, ...profile };
    saveUser(user);
    userName = profile.name?.split(' ')[0] || 'there';
    renderDynamicGreeting(userName);
    calorieGoal = profile.daily_calorie_target || 2200;

    const stepsGoal = profile.notification_preferences?.targets?.target_steps || user.notification_preferences?.targets?.target_steps || 10000;
    const goalEl = document.getElementById('steps-goal-label');
    if (goalEl) goalEl.textContent = `Goal: ${stepsGoal.toLocaleString()}`;
  } catch { /* fall back to cached/default goal */ }

  // Persist today's Good Morning insight exactly once, at the first page load after midnight.
  // Uses a localStorage date-key so it never re-triggers on subsequent logins the same day.
  await checkAndPersistMorningInsight(userName).catch(() => {});

  // 1. Fetch Vitals (for user's local date)
  let latestWeight = null;
  let adaptedVitals = null;
  const today = todayISO();
  try {
    const v = await api.get('/vitals/latest?date_str=' + today);
    adaptedVitals = adaptVitals(v);
    renderVitals(adaptedVitals);
    latestWeight = v.weight;
  } catch {
    document.getElementById('last-sync').textContent = 'No Google Health / Scale data yet';
  }

  // 2. BMI
  renderBmi(latestWeight ?? user.weight, user.height);

  // 3. Fetch Meals (today only, reset at 12:00 AM local time)
  let todayMeals = null;
  try {
    const rawMeals = await api.get('/meals/');
    todayMeals = rawMeals.filter(m => getLocalTimestampDate(m.logged_at) === today).map(adaptMeal);
    _lastMeals = todayMeals; // keep a fresh copy for the 30s poll
    await renderNutrition(todayMeals, calorieGoal);
    renderRecentMeals(todayMeals);
  } catch {
    await renderNutrition([], calorieGoal);
    document.getElementById('recent-meals').innerHTML = '<div class="card center muted">Could not load meals.</div>';
  }

  // 4. Ensure guaranteed daily insights (Morning, Midday Meal, Steps, Calories) are evaluated & persisted
  if (todayMeals !== null) {
    _lastVitals = adaptedVitals;
    await checkAndPersistDailyInsights({
      userProfile: user,
      userName,
      vitalsData: adaptedVitals,
      mealsData: todayMeals,
      calorieTarget: calorieGoal,
    }).catch(() => {});
  }

  // 5. Fetch Authoritative Top Recommendation from server
  try {
    const topRec = await api.get('/recommendations/top');
    if (topRec) {
      if (topRec.rule_id !== 'lifestyle.set_daily_targets') {
        localStorage.setItem('vita_targets_cleared', '1');
      }
      renderRec(topRec);
    } else {
      renderRecFallback();
    }
  } catch {
    renderRecFallback();
  }

  initLucide();
}

loadAll();

async function syncNow() {
  setSyncingState(true);
  try {
    // Trigger Google Health sync + get fresh vitals in one call
    const result = await api.post('/vitals/sync-all', {});
    if (result.vitals) {
      _lastVitals = adaptVitals(result.vitals);
      renderVitals(_lastVitals);
      renderBmi(result.vitals.weight ?? user.weight, user.height);
    }
    // Also refresh meals, recommendations, profile
    await loadAll();
    if (result.google_synced) {
      toast(`Synced ${result.synced_count} data point(s) from Google Health`);
    } else {
      toast('Device readings refreshed');
    }
  } catch {
    toast('Sync failed — check connection', 'error');
  } finally {
    setSyncingState(false);
    initLucide();
  }
}

document.getElementById('sync-btn')?.addEventListener('click', () => syncNow());
document.getElementById('sync-btn-2')?.addEventListener('click', () => syncNow());

// Poll vitals every 30s; also checks for time slot crossovers and updates dashboard insight
setInterval(async () => {
  try {
    const v = await api.get('/vitals/latest?date_str=' + todayISO());
    _lastVitals = adaptVitals(v);
    renderVitals(_lastVitals);
    renderBmi(v.weight ?? user.weight, user.height);
  } catch { /* ignore */ }

  const firstName = user.name?.split(' ')[0] || 'there';
  await checkAndPersistDailyInsights({
    userProfile: user,
    userName: firstName,
    vitalsData: _lastVitals,
    mealsData: _lastMeals,
    calorieTarget: user.daily_calorie_target || 2200,
  }).catch(() => {});

  try {
    const topRec = await api.get('/recommendations/top');
    if (topRec) {
      if (topRec.rule_id !== 'lifestyle.set_daily_targets') {
        localStorage.setItem('vita_targets_cleared', '1');
      }
      renderRec(topRec);
    }
  } catch { /* ignore */ }
}, 30000);

