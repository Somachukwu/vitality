import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { vitalsStatus, formatDate, toast, applyStoredTheme, initThemeToggle, waitForChart } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('vitals.html');
initThemeToggle();

const charts = {};

// ── Chart Fullscreen / Landscape Expand ───────────────────────────────────────
function onFullscreenStateChange(isFullscreen) {
  // Reset any stray inline canvas sizes that Chart.js or browser left
  document.querySelectorAll('.chart-canvas canvas').forEach(canvas => {
    canvas.style.width = '100%';
    canvas.style.maxWidth = '100%';
  });

  // Update expand button icons
  document.querySelectorAll('.btn-chart-fullscreen').forEach(btn => {
    const icon = btn.querySelector('i[data-lucide]');
    if (icon) {
      icon.setAttribute('data-lucide', isFullscreen ? 'minimize-2' : 'maximize-2');
      if (window.lucide) window.lucide.createIcons();
    }
  });

  // Trigger resize on charts
  setTimeout(() => {
    Object.values(charts).forEach(c => {
      if (c && typeof c.resize === 'function') {
        c.resize();
      }
    });
  }, 100);
}

window.expandChart = async function (cardId, canvasId) {
  const card = document.getElementById(cardId);
  if (!card) return;

  const isAlreadyFull = document.fullscreenElement === card || card.classList.contains('chart-pseudo-fullscreen');

  if (!isAlreadyFull) {
    try {
      if (card.requestFullscreen) {
        await card.requestFullscreen();
      } else if (card.webkitRequestFullscreen) {
        await card.webkitRequestFullscreen();
      } else {
        card.classList.add('chart-pseudo-fullscreen');
        onFullscreenStateChange(true);
      }
    } catch {
      card.classList.add('chart-pseudo-fullscreen');
      onFullscreenStateChange(true);
    }

    // Attempt locking screen to landscape on mobile devices
    if (screen.orientation && screen.orientation.lock) {
      try {
        await screen.orientation.lock('landscape');
      } catch { /* unsupported or requires permission */ }
    }
  } else {
    if (document.fullscreenElement) {
      try {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (document.webkitExitFullscreen) await document.webkitExitFullscreen();
      } catch { /* ignore */ }
    }
    card.classList.remove('chart-pseudo-fullscreen');
    onFullscreenStateChange(false);

    if (screen.orientation && screen.orientation.unlock) {
      try { screen.orientation.unlock(); } catch { /* ignore */ }
    }
  }
};

document.addEventListener('fullscreenchange', () => {
  const isFullscreen = !!document.fullscreenElement;
  onFullscreenStateChange(isFullscreen);
  if (!isFullscreen) {
    document.querySelectorAll('.chart-pseudo-fullscreen').forEach(el => el.classList.remove('chart-pseudo-fullscreen'));
    if (screen.orientation && screen.orientation.unlock) {
      try { screen.orientation.unlock(); } catch { /* ignore */ }
    }
  }
});


function makeChart(id, label, data, color) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  const grad = ctx.getContext('2d').createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, color + '55');
  grad.addColorStop(1, color + '00');
  charts[id] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.label),
      datasets: [{ label, data: data.map(d => d.value), borderColor: color, backgroundColor: grad, fill: true, tension: 0.35, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { family: 'JetBrains Mono', size: 10 } }, grid: { display: false } },
        y: { ticks: { font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' }, beginAtZero: false },
      },
      animation: { duration: 700 },
    },
  });
}

/**
 * Build a Chart.js line chart for continuous (per-reading) data.
 * X-axis labels are datetime-aware with granularity based on range.
 */
function makeContinuousChart(id, label, data, color, days) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  const grad = ctx.getContext('2d').createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, color + '55');
  grad.addColorStop(1, color + '00');

  const timeLabels = data.map(d => {
    const dt = new Date(d.recorded_at);
    if (days <= 1) {
      return dt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } else if (days <= 7) {
      return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
             dt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } else {
      return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }
  });

  charts[id] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timeLabels,
      datasets: [{
        label,
        data: data.map(d => d.value),
        borderColor: color,
        backgroundColor: grad,
        fill: true,
        tension: 0.35,
        borderWidth: 2,
        pointRadius: data.length > 100 ? 0 : 3,
        pointHoverRadius: 5,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: days <= 1 ? 12 : 10,
            maxRotation: 45,
            font: { family: 'JetBrains Mono', size: 9 },
          },
          grid: { display: false },
        },
        y: {
          ticks: { font: { family: 'JetBrains Mono', size: 10 } },
          grid: { color: 'rgba(0,0,0,0.05)' },
          beginAtZero: false,
        },
      },
      animation: { duration: 700 },
    },
  });
}

function makeBarChart(id, label, data, color) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.label),
      datasets: [{ label, data: data.map(d => d.value), backgroundColor: color + 'AA', borderColor: color, borderWidth: 1, borderRadius: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { family: 'JetBrains Mono', size: 10 } }, grid: { display: false } },
        y: { ticks: { font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' }, beginAtZero: true },
      },
      animation: { duration: 700 },
    },
  });
}

function makeSleepChart(id, sleepHistory) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();

  const labels = sleepHistory.map(h => dateLabel(h.date));
  const hasStages = sleepHistory.some(h => (h.deep_min || 0) + (h.rem_min || 0) + (h.light_min || 0) > 0);

  if (hasStages) {
    charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Deep (h)',  data: sleepHistory.map(h => Number(((h.deep_min || 0) / 60).toFixed(2))),  backgroundColor: '#312E81' },
          { label: 'REM (h)',   data: sleepHistory.map(h => Number(((h.rem_min || 0) / 60).toFixed(2))),   backgroundColor: '#6366F1' },
          { label: 'Light (h)', data: sleepHistory.map(h => Number(((h.light_min || 0) / 60).toFixed(2))), backgroundColor: '#93C5FD' },
          { label: 'Awake (h)', data: sleepHistory.map(h => Number(((h.awake_min || 0) / 60).toFixed(2))), backgroundColor: '#CBD5E1' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: true, position: 'top', labels: { font: { family: 'DM Sans', size: 11 }, boxWidth: 10 } } },
        scales: {
          x: { stacked: true, ticks: { maxTicksLimit: 10, font: { family: 'JetBrains Mono', size: 10 } }, grid: { display: false } },
          y: { stacked: true, ticks: { font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' }, beginAtZero: true },
        },
        animation: { duration: 700 },
      },
    });
  } else {
    const totalHours = sleepHistory.map(h => Number(((h.sleep_duration_min || 0) / 60).toFixed(2)));
    charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ label: 'Sleep (hours)', data: totalHours, backgroundColor: '#6366F1AA', borderColor: '#6366F1', borderWidth: 1, borderRadius: 4 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 10, font: { family: 'JetBrains Mono', size: 10 } }, grid: { display: false } },
          y: { ticks: { font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' }, beginAtZero: true },
        },
        animation: { duration: 700 },
      },
    });
  }
}

function dateLabel(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

async function render(days) {
  // ── Fetch continuous HR / SpO₂ readings AND daily history in parallel ──
  let continuous = [];
  let history = [];
  try {
    [continuous, history] = await Promise.all([
      api.get(`/vitals/continuous?days=${days}`),
      api.get(`/vitals/history?days=${days}`),
    ]);
  } catch {
    document.getElementById('anomalies').innerHTML = `<div class="muted text-sm">Could not load vitals history.</div>`;
    return;
  }

  if (!history.length && !continuous.length) {
    document.getElementById('anomalies').innerHTML = `<div class="muted text-sm">No data for this period. Connect your ESP32 or sync Google Health to start recording.</div>`;
    return;
  }

  if (await waitForChart()) {
    // ── Continuous line charts for HR & SpO₂ (per-reading granularity) ──
    const hrData   = continuous.filter(c => c.heart_rate != null).map(c => ({ recorded_at: c.recorded_at, value: c.heart_rate }));
    const spo2Data = continuous.filter(c => c.spo2 != null).map(c => ({ recorded_at: c.recorded_at, value: c.spo2 }));

    if (hrData.length) {
      makeContinuousChart('c-hr', 'Heart rate', hrData, '#E53E3E', days);
    } else {
      // Fall back to daily summary if no continuous data exists yet
      const hrDaily = history.filter(h => h.heart_rate != null).map(h => ({ label: dateLabel(h.date), value: h.heart_rate }));
      makeChart('c-hr', 'Heart rate', hrDaily, '#E53E3E');
    }

    if (spo2Data.length) {
      makeContinuousChart('c-spo2', 'SpO\u2082', spo2Data, '#00BFA5', days);
    } else {
      const spo2Daily = history.filter(h => h.spo2 != null).map(h => ({ label: dateLabel(h.date), value: h.spo2 }));
      makeChart('c-spo2', 'SpO\u2082', spo2Daily, '#00BFA5');
    }

    // ── Daily-summary charts (unchanged) ────────────────────────────────
    const tempData = history.filter(h => h.temperature != null).map(h => ({ label: dateLabel(h.date), value: h.temperature }));
    const wtData   = history.filter(h => h.weight != null).map(h => ({ label: dateLabel(h.date), value: h.weight }));

    makeChart('c-temp', 'Temperature', tempData, '#D97706');
    makeChart('c-wt',   'Weight',      wtData,   '#1B4332');

    // Sleep history & stages
    const sleepHistory = history.filter(h => h.sleep_duration_min != null && h.sleep_duration_min > 0);
    if (sleepHistory.length) {
      makeSleepChart('c-sleep', sleepHistory);
    } else {
      const el = document.getElementById('c-sleep');
      if (el) el.parentElement.innerHTML = '<div class="center muted text-sm">No sleep records for this period.</div>';
    }

    // Daily aggregate bar charts
    const stepsData  = history.filter(h => h.steps != null).map(h => ({ label: dateLabel(h.date), value: h.steps }));
    const distData   = history.filter(h => h.distance_km != null).map(h => ({ label: dateLabel(h.date), value: h.distance_km }));
    const calData    = history.filter(h => h.calories_burned != null).map(h => ({ label: dateLabel(h.date), value: h.calories_burned }));
    const activeData = history.filter(h => h.active_minutes != null).map(h => ({ label: dateLabel(h.date), value: h.active_minutes }));
    const floorsData = history.filter(h => h.floors != null).map(h => ({ label: dateLabel(h.date), value: h.floors }));

    makeBarChart('c-steps',  'Steps',          stepsData,  '#6366F1');
    makeBarChart('c-dist',   'Distance',       distData,   '#10B981');
    makeBarChart('c-cal',    'Calories',       calData,    '#EF4444');
    makeBarChart('c-active', 'Active minutes', activeData, '#F59E0B');
    makeBarChart('c-floors', 'Floors',         floorsData, '#8B5CF6');
  } else {
    ['c-hr', 'c-spo2', 'c-sleep', 'c-active', 'c-temp', 'c-wt', 'c-steps', 'c-cal', 'c-dist', 'c-floors'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.parentElement.innerHTML = '<div class="center muted text-sm">Chart unavailable.</div>';
    });
  }

  // Anomaly detection from daily history (unchanged)
  const anomalies = history.filter(h =>
    (h.heart_rate   != null && vitalsStatus('heartRate',   h.heart_rate)   !== 'green') ||
    (h.spo2         != null && vitalsStatus('spo2',        h.spo2)        !== 'green') ||
    (h.temperature  != null && vitalsStatus('temperature', h.temperature) !== 'green')
  ).slice(-8).reverse();

  const host = document.getElementById('anomalies');
  if (!anomalies.length) {
    host.innerHTML = `<div class="muted text-sm">No anomalies detected in this period.</div>`;
  } else {
    host.innerHTML = anomalies.map(a => {
      const issues = [];
      if (a.heart_rate   != null && vitalsStatus('heartRate',   a.heart_rate)   !== 'green') issues.push(`HR ${a.heart_rate} bpm`);
      if (a.spo2         != null && vitalsStatus('spo2',        a.spo2)         !== 'green') issues.push(`SpO\u2082 ${a.spo2.toFixed(1)}%`);
      if (a.temperature  != null && vitalsStatus('temperature', a.temperature)  !== 'green') issues.push(`Temp ${a.temperature.toFixed(1)}\u00b0C`);
      return `<div class="list-item">
        <span class="dot dot-amber"></span>
        <div style="flex:1"><div style="font-weight:600">${issues.join(' \u00b7 ')}</div>
        <div class="text-xs muted">${dateLabel(a.date)}</div></div>
      </div>`;
    }).join('');
  }
  document.getElementById('last-sync').textContent = 'Updated ' + formatDate(new Date().toISOString());
}

document.getElementById('range').addEventListener('change', (e) => render(Number(e.target.value)));
render(7);

