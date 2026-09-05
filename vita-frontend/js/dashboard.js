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

  const initialCard = resolveContextualCard({
    userProfile: user,
    topRec: null,
    vitalsData: null,
    mealsData: [],
    calorieTarget: user.daily_calorie_target || 2200,
  });
  if (initialCard) {
    renderRec(initialCard);
  }
} catch { /* ignore */ }


let macrosChart = null;

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
  const morningCard = getRotatingMorningInsight(firstName);
  await persistContextualInsight(morningCard);
  localStorage.setItem(key, '1');
}

let recSwitchTimer = null;

function renderSingleRecContent(rec) {
  const textEl = document.getElementById('rec-text');
  const triggerEl = document.getElementById('rec-trigger');
  const badgeEl = document.getElementById('rec-badge');
  if (!textEl) return;

  if (badgeEl) {
    const isCritical = rec.tier === 'safety' || rec.priority === 'critical' || rec.severity === 'critical';
    const defaultBadge = rec.rule_id === 'lifestyle.set_daily_targets' ? 'Getting Started' : (isCritical ? 'Health Alert 🚨' : "Today's tip");
    const badgeText = rec.badge || defaultBadge;
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
      actionBtn = `<a href="${cleanRoute}" style="background:#ffffff; color:#1B4332; font-weight:700; padding:0.35rem 0.85rem; border-radius:999px; text-decoration:none; display:inline-flex; align-items:center; gap:0.35rem; font-size:0.8125rem; box-shadow:0 2px 8px rgba(0,0,0,0.18);">${rec.action_data.action_label || 'View Details'} →</a>`;
    }
    const viewAllLink = `<a href="recommendations.html" style="color:rgba(255,255,255,0.9); font-size:0.8125rem; text-decoration:underline; font-weight:500">All insights</a>`;
    triggerEl.innerHTML = `<div class="row between align-center mt-2">${actionBtn || '<span></span>'}${viewAllLink}</div>`;
  }
  initLucide();
}

function renderRec(cardResult) {
  if (recSwitchTimer) {
    clearInterval(recSwitchTimer);
    recSwitchTimer = null;
  }

  // Remove any previous tab toggle bar
  const oldSwitcher = document.getElementById('rec-switcher-controls');
  if (oldSwitcher) oldSwitcher.remove();

  if (!cardResult) {
    renderRecFallback();
    return;
  }

  // If alternating between Critical Alert and Morning Greeting
  if (cardResult.isAlternating && Array.isArray(cardResult.cards) && cardResult.cards.length > 1) {
    const cards = cardResult.cards;
    let activeIndex = 0;

    const recCardEl = document.getElementById('rec-card');
    const switcher = document.createElement('div');
    switcher.id = 'rec-switcher-controls';
    switcher.className = 'row gap-xs mb-2 align-center';

    cards.forEach((c, idx) => {
      const btn = document.createElement('button');
      btn.id = `rec-tab-btn-${idx}`;
      btn.type = 'button';
      btn.className = `btn btn-xs`;
      btn.style.cssText = `padding:0.22rem 0.65rem; border-radius:999px; font-size:0.75rem; transition:all 0.25s ease; ${idx === 0 ? 'background:rgba(255,255,255,0.3); color:#fff; font-weight:700; border:1px solid rgba(255,255,255,0.4);' : 'background:rgba(255,255,255,0.1); color:rgba(255,255,255,0.75); border:1px solid transparent;'}`;
      btn.innerHTML = c.tabLabel || (c.tier === 'safety' ? '🚨 Critical Alert' : '☀️ Morning Tip');
      btn.onclick = (e) => {
        e.stopPropagation();
        switchToIndex(idx);
      };
      switcher.appendChild(btn);
    });

    recCardEl.insertBefore(switcher, recCardEl.firstChild);

    function switchToIndex(idx) {
      activeIndex = idx;
      cards.forEach((_, i) => {
        const b = document.getElementById(`rec-tab-btn-${i}`);
        if (b) {
          b.style.background = i === idx ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.1)';
          b.style.color = i === idx ? '#fff' : 'rgba(255,255,255,0.75)';
          b.style.fontWeight = i === idx ? '700' : '500';
          b.style.borderColor = i === idx ? 'rgba(255,255,255,0.4)' : 'transparent';
        }
      });
      renderSingleRecContent(cards[idx]);
    }

    renderSingleRecContent(cards[0]);

    // Automatically alternate between Morning Greeting and Critical Alert every 6 seconds
    recSwitchTimer = setInterval(() => {
      const nextIdx = (activeIndex + 1) % cards.length;
      switchToIndex(nextIdx);
    }, 6000);
  } else {
    renderSingleRecContent(cardResult);
  }
}

function resolveContextualCard({ userProfile, topRec, vitalsData, mealsData, calorieTarget }) {
  const now = new Date();
  const hour = now.getHours();
  const firstName = userProfile.name?.split(' ')[0] || 'there';
  const goal = userProfile.goal_type || 'maintenance';
  const savedTargets = userProfile.notification_preferences?.targets || {};
  const targetSteps = savedTargets.target_steps || 10000;
  const targetProtein = savedTargets.target_protein || Math.round((userProfile.weight || 70) * 1.4);
  const steps = vitalsData?.steps || 0;
  const sleepHours = vitalsData?.sleepDurationMin ? Number((vitalsData.sleepDurationMin / 60).toFixed(1)) : 0;
  const consumedCals = Math.round((mealsData || []).reduce((sum, m) => sum + (m.totalCalories || 0), 0));
  const consumedProtein = Math.round((mealsData || []).flatMap(m => m.detectedFoods).reduce((sum, f) => sum + (f.protein || 0), 0));
  const mealsCount = (mealsData || []).length;

  const isCritical = topRec && (topRec.tier === 'safety' || topRec.priority === 'critical' || topRec.severity === 'critical');
  const today = todayISO();
  const joinDate = userProfile.created_at ? getLocalTimestampDate(userProfile.created_at) : '';
  const isJoinedToday = joinDate === today;

  // 1. New user who joined TODAY and has not configured targets yet:
  // Show default getting started message on Day 1
  if (isJoinedToday && !userProfile.daily_calorie_target) {
    if (topRec?.rule_id === 'lifestyle.set_daily_targets') {
      return topRec;
    }
    return {
      badge: 'Getting Started 🚀',
      title: 'Set Your Daily Health Targets',
      message: 'Personalize your daily calorie, macro, step, and sleep targets to start tracking your progress and receive tailored AI health insights.',
      action_data: { action_label: 'Configure Targets', route: 'goals.html?edit=1' },
      rule_id: 'lifestyle.set_daily_targets',
    };
  }

  // 2. Critical Safety Alert always overrides everything
  if (isCritical) return topRec;

  // 3. Latest-wins: if a recommendation was triggered/persisted today, show it.
  //    The morning insight is persisted at 12:00 AM, so at the start of the day
  //    topRec will already be the morning card. As the day progresses and new
  //    insights are triggered (milestones, evening cards, backend rules), they are
  //    persisted and become the new topRec on the next refresh cycle.
  if (topRec && topRec.created_at && getLocalTimestampDate(topRec.created_at) === today) {
    return topRec;
  }


  // 4. Multi-Target Milestone Celebrations (After meals or activity logged)
  // A. Steps Target Milestone
  if (targetSteps > 0 && steps >= targetSteps) {
    return {
      badge: 'Milestone Achieved ⭐',
      title: 'Daily Step Goal Crushed! 🎉',
      message: `Incredible work, ${firstName}! You’ve hit ${steps.toLocaleString()} steps, surpassing your daily target of ${targetSteps.toLocaleString()}. Consistent movement powers cardiovascular endurance and metabolic vitality.`,
      action_data: { action_label: 'View Activity', route: 'vitals.html' },
      rule_id: 'milestone.steps_met',
    };
  }

  // B. Protein Target Milestone
  if (targetProtein > 0 && consumedProtein >= targetProtein && mealsCount >= 2) {
    return {
      badge: 'Macro Milestone 🥩',
      title: 'Protein Target Achieved! 💪',
      message: `Great work, ${firstName}! You logged ${consumedProtein}g of protein today, meeting your target for muscle preservation and cellular repair.`,
      action_data: { action_label: 'View Food Log', route: 'food-log.html' },
      rule_id: 'milestone.protein_met',
    };
  }

  // C. Calorie Target Hit (Within ±100 kcal with >= 2 meals)
  if (calorieTarget > 0 && mealsCount >= 2 && Math.abs(consumedCals - calorieTarget) <= 100) {
    return {
      badge: 'Energy Balance 🎯',
      title: 'Calorie Target Hit! ⚖️',
      message: `Spot on, ${firstName}! You’ve hit your daily energy intake target (${consumedCals.toLocaleString()} / ${calorieTarget.toLocaleString()} kcal) with precision.`,
      action_data: { action_label: 'View Nutrition', route: 'food-log.html' },
      rule_id: 'milestone.calories_met',
    };
  }

  // 5. Time-Specific Dynamic Afternoon & Evening Cards
  // A. Evening Step Push (6:00 PM – 11:59 PM)
  if (hour >= 18 && targetSteps > 0 && steps < targetSteps) {
    const remaining = targetSteps - steps;
    return {
      badge: 'Evening Boost 🚶‍♂️',
      title: 'Evening Step Boost',
      message: `You’re at ${steps.toLocaleString()} steps—just ${remaining.toLocaleString()} steps away from reaching your daily target of ${targetSteps.toLocaleString()}! A pleasant evening stroll after dinner will carry you across the finish line.`,
      action_data: { action_label: 'Track Activity', route: 'vitals.html' },
      rule_id: 'time.evening_steps_push',
    };
  }

  // B. Evening 7:00 PM Calorie Guidance (7:00 PM – 11:59 PM)
  if (hour >= 19 && calorieTarget > 0) {
    if (goal === 'weight_loss' && consumedCals >= calorieTarget * 0.95) {
      return {
        badge: 'Calorie Target 🎯',
        title: 'Calorie Target Locked In',
        message: `You've hit your fat loss energy target for today (${consumedCals} / ${calorieTarget} kcal). Close your eating window for the night to protect your calorie deficit and promote overnight fat oxidation.`,
        action_data: { action_label: 'View Nutrition', route: 'food-log.html' },
        rule_id: 'time.evening_deficit_lock',
      };
    }
    if (goal === 'weight_gain' && consumedCals < calorieTarget * 0.80) {
      const remaining = calorieTarget - consumedCals;
      return {
        badge: 'Hypertrophy Fuel 🥩',
        title: 'Fuel Your Muscle Growth',
        message: `7 PM hypertrophy check: You're currently ${remaining} kcal below your surplus target. Add a nutrient-rich evening meal or protein shake to support overnight muscle protein synthesis.`,
        action_data: { action_label: 'Log Evening Snack', route: 'food-log.html' },
        rule_id: 'time.evening_surplus_needed',
      };
    }
    if (goal === 'maintenance' && consumedCals < calorieTarget * 0.65) {
      const remaining = calorieTarget - consumedCals;
      return {
        badge: 'Nutrition Reminder 🍽️',
        title: 'Evening Nutrition Reminder',
        message: `It's past 7 PM and you're running a significant calorie deficit (${remaining} kcal remaining). Log your dinner or an evening snack to support metabolism and recovery.`,
        action_data: { action_label: 'Log Meal', route: 'food-log.html' },
        rule_id: 'time.evening_general_deficit',
      };
    }
    if (consumedCals > calorieTarget * 1.05) {
      return {
        badge: 'Energy Balance 🍵',
        title: 'Daily Energy Target Reached',
        message: `You've met your daily calorie target (${consumedCals} / ${calorieTarget} kcal). To prevent excess weight gain and aid digestive rest, switch to water or herbal tea for the evening.`,
        action_data: { action_label: 'View Nutrition', route: 'food-log.html' },
        rule_id: 'time.evening_surplus_cap',
      };
    }
  }

  // C. Midday (12:00 PM – 2:59 PM) & Afternoon (3:00 PM – 5:59 PM) Meal Reminders (only if 0 meals logged)
  if (hour >= 12 && hour < 15 && mealsCount === 0) {
    return {
      badge: 'Fuel Check-In 🥗',
      title: 'Midday Fuel Check-In',
      message: `It’s noon and no meals are logged yet, ${firstName}. If you aren't fasting, take a moment to nourish your body and snap a photo of your lunch to keep your energy steady.`,
      action_data: { action_label: 'Log Lunch', route: 'food-log.html' },
      rule_id: 'time.midday_meal_prompt',
    };
  }
  if (hour >= 15 && hour < 18 && mealsCount === 0) {
    return {
      badge: 'Energy Check-In 🕒',
      title: 'Afternoon Energy Check-In',
      message: `3:00 PM check-in: No meals logged so far today. Staying fueled prevents afternoon energy dips and evening overeating. Remember to log your meals!`,
      action_data: { action_label: 'Log Meal', route: 'food-log.html' },
      rule_id: 'time.afternoon_meal_prompt',
    };
  }

  // D. Short Sleep (< 6.5 hours) Guidance (if sleep recorded)
  if (sleepHours > 0 && sleepHours < 6.5 && hour < 14) {
    if (goal === 'lose' || goal === 'weight_loss') {
      return {
        badge: 'Sleep & Metabolism 🌙',
        title: 'Short Sleep & Appetite Regulation',
        message: `You logged ${sleepHours} hours of sleep last night. In a calorie deficit, short sleep (<6.5h) elevates the hunger hormone ghrelin. Aim for 8.0-8.5 hours tonight to protect lean muscle and keep appetite stable.`,
        action_data: { action_label: 'View Sleep', route: 'vitals.html' },
        rule_id: 'sleep.short_loss',
      };
    } else if (goal === 'gain' || goal === 'weight_gain') {
      return {
        badge: 'Recovery Alert 🌙',
        title: 'Short Sleep & Muscle Recovery',
        message: `You logged ${sleepHours} hours of sleep last night. Over 70% of growth hormone release occurs during deep sleep. Prioritize 8.5-9.0 hours of restorative sleep tonight to maximize hypertrophy gains.`,
        action_data: { action_label: 'View Sleep', route: 'vitals.html' },
        rule_id: 'sleep.short_gain',
      };
    } else {
      return {
        badge: 'Restorative Rest 🌙',
        title: 'Prioritize Restorative Sleep Tonight',
        message: `You logged ${sleepHours} hours of sleep last night. Short sleep (<6.5h) elevates cortisol and slows recovery. Aim for an earlier, calming wind-down routine tonight.`,
        action_data: { action_label: 'View Sleep', route: 'vitals.html' },
        rule_id: 'sleep.short_wellness',
      };
    }
  }

  // 6. Return most recent top recommendation from backend, or morning insight fallback
  return topRec || getRotatingMorningInsight(firstName);
}

function renderRecFallback() {
  const textEl = document.getElementById('rec-text');
  const triggerEl = document.getElementById('rec-trigger');
  const badgeEl = document.getElementById('rec-badge');
  if (!textEl) return;

  if (badgeEl) {
    badgeEl.innerHTML = '<i data-lucide="sparkles"></i> Getting Started';
    badgeEl.style.color = '';
    badgeEl.style.background = '';
    badgeEl.style.borderColor = '';
  }

  textEl.innerHTML = '<strong style="display:block; margin-bottom:0.25rem; font-size:1.05rem">Set Your Daily Health Targets</strong><span>Personalize your daily calorie, macro, step, and sleep targets to start tracking your progress and receive tailored AI health insights.</span>';

  if (triggerEl) {
    triggerEl.innerHTML = '<div class="row between align-center mt-2"><a href="goals.html?edit=1" style="background:#ffffff; color:#1B4332; font-weight:700; padding:0.35rem 0.85rem; border-radius:999px; text-decoration:none; display:inline-flex; align-items:center; gap:0.35rem; font-size:0.8125rem; box-shadow:0 2px 8px rgba(0,0,0,0.18);">Configure Targets →</a><a href="goals.html" style="color:rgba(255,255,255,0.9); font-size:0.8125rem; text-decoration:underline; font-weight:500">View Goals</a></div>';
  }
  initLucide();
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
    card.rule_id.startsWith('vitals.')
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
  let todayMeals = [];
  try {
    const rawMeals = await api.get('/meals/');
    todayMeals = rawMeals.filter(m => getLocalTimestampDate(m.logged_at) === today).map(adaptMeal);
    await renderNutrition(todayMeals, calorieGoal);
    renderRecentMeals(todayMeals);
  } catch {
    await renderNutrition([], calorieGoal);
    document.getElementById('recent-meals').innerHTML = '<div class="card center muted">Could not load meals.</div>';
  }

  // 4. Fetch Top Recommendation & Resolve Contextual Smart Card
  try {
    let topRec = null;
    try {
      topRec = await api.get('/recommendations/top');
    } catch { /* ignore */ }

    const smartCard = resolveContextualCard({
      userProfile: user,
      topRec,
      vitalsData: adaptedVitals,
      mealsData: todayMeals,
      calorieTarget: calorieGoal,
    });

    if (smartCard) {
      renderRec(smartCard);
      // Persist to database so it is recorded in Insights history
      if (smartCard.isAlternating && Array.isArray(smartCard.cards)) {
        smartCard.cards.forEach(c => persistContextualInsight(c));
      } else {
        persistContextualInsight(smartCard);
      }
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
      renderVitals(adaptVitals(result.vitals));
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



document.getElementById('sync-btn').addEventListener('click', (e) => syncNow(e.currentTarget));
document.getElementById('sync-btn-2').addEventListener('click', (e) => syncNow(e.currentTarget));

// Poll vitals every 30s; also checks for midnight crossover to persist morning insight
setInterval(async () => {
  try {
    const v = await api.get('/vitals/latest?date_str=' + todayISO());
    renderVitals(adaptVitals(v));
    renderBmi(v.weight ?? user.weight, user.height);
  } catch { /* ignore */ }
  // If midnight just rolled over, persist the morning insight for the new day
  const firstName = user.name?.split(' ')[0] || 'there';
  checkAndPersistMorningInsight(firstName).catch(() => {});
}, 30000);
