import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { vitalsStatus, formatDate, toast, applyStoredTheme, initThemeToggle, waitForChart } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('vitals.html');
initThemeToggle();

const charts = {};

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

function dateLabel(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

async function render(days) {
  let history = [];
  try {
    history = await api.get(`/vitals/history?days=${days}`);
  } catch {
    document.getElementById('anomalies').innerHTML = `<div class="muted text-sm">Could not load vitals history.</div>`;
    return;
  }

  if (!history.length) {
    document.getElementById('anomalies').innerHTML = `<div class="muted text-sm">No data for this period. Connect your ESP32 or sync Google Health to start recording.</div>`;
    return;
  }

  if (await waitForChart()) {
    // Point-in-time line charts
    const hrData   = history.filter(h => h.heart_rate != null).map(h => ({ label: dateLabel(h.date), value: h.heart_rate }));
    const spo2Data = history.filter(h => h.spo2 != null).map(h => ({ label: dateLabel(h.date), value: h.spo2 }));
    const tempData = history.filter(h => h.temperature != null).map(h => ({ label: dateLabel(h.date), value: h.temperature }));
    const wtData   = history.filter(h => h.weight != null).map(h => ({ label: dateLabel(h.date), value: h.weight }));

    makeChart('c-hr',   'Heart rate',  hrData,   '#E53E3E');
    makeChart('c-spo2', 'SpO\u2082',   spo2Data, '#00BFA5');
    makeChart('c-temp', 'Temperature', tempData, '#D97706');
    makeChart('c-wt',   'Weight',      wtData,   '#1B4332');

    // Daily aggregate bar charts
    const stepsData = history.filter(h => h.steps != null).map(h => ({ label: dateLabel(h.date), value: h.steps }));
    const calData   = history.filter(h => h.calories_burned != null).map(h => ({ label: dateLabel(h.date), value: h.calories_burned }));
    const distData  = history.filter(h => h.distance_km != null).map(h => ({ label: dateLabel(h.date), value: h.distance_km }));

    makeBarChart('c-steps', 'Steps',    stepsData, '#6366F1');
    makeBarChart('c-cal',   'Calories', calData,   '#EF4444');
    makeBarChart('c-dist',  'Distance', distData,  '#10B981');
  } else {
    ['c-hr', 'c-spo2', 'c-temp', 'c-wt', 'c-steps', 'c-cal', 'c-dist'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.parentElement.innerHTML = '<div class="center muted text-sm">Chart unavailable.</div>';
    });
  }

  // Anomaly detection from history
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
document.getElementById('sync').addEventListener('click', async () => {
  const btn = document.getElementById('sync');
  btn.disabled = true;
  btn.textContent = 'Syncing…';
  try {
    await api.post('/vitals/sync-all', {});
    await render(Number(document.getElementById('range').value));
    toast('Data synced successfully');
  } catch {
    toast('Sync failed', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i data-lucide="refresh-cw"></i> Sync';
    if (window.lucide) window.lucide.createIcons();
  }
});
render(7);
