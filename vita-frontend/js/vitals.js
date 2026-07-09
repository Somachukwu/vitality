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
  if (charts[id]) charts[id].destroy();
  const grad = ctx.getContext('2d').createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, color + '55');
  grad.addColorStop(1, color + '00');
  charts[id] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => new Date(d.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit' })),
      datasets: [{ label, data: data.map(d => d.value), borderColor: color, backgroundColor: grad, fill: true, tension: 0.35, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { family: 'JetBrains Mono', size: 10 } }, grid: { display: false } },
        y: { ticks: { font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
      },
      animation: { duration: 700 },
    },
  });
}

async function render(days) {
  let history = [];
  try {
    const raw = await api.get(`/vitals/history?days=${days}`);
    // Adapt API snake_case to camelCase
    history = raw.map(h => ({
      timestamp:   h.recorded_at,
      heartRate:   h.heart_rate  ?? null,
      spo2:        h.spo2        ?? null,
      temperature: h.temperature ?? null,
      humidity:    h.humidity    ?? null,
      weight:      h.weight      ?? null,
    }));
  } catch {
    document.getElementById('anomalies').innerHTML = `<div class="muted text-sm">Could not load vitals history.</div>`;
    return;
  }

  if (!history.length) {
    document.getElementById('anomalies').innerHTML = `<div class="muted text-sm">No data for this period. Connect your ESP32 to start recording.</div>`;
    return;
  }

  if (await waitForChart()) {
    makeChart('c-hr',   'Heart rate',  history.filter(h => h.heartRate   != null).map(h => ({ timestamp: h.timestamp, value: h.heartRate   })), '#E53E3E');
    makeChart('c-spo2', 'SpO2',        history.filter(h => h.spo2        != null).map(h => ({ timestamp: h.timestamp, value: h.spo2        })), '#00BFA5');
    makeChart('c-temp', 'Temperature', history.filter(h => h.temperature != null).map(h => ({ timestamp: h.timestamp, value: h.temperature })), '#D97706');
    makeChart('c-wt',   'Weight',      history.filter(h => h.weight      != null).map(h => ({ timestamp: h.timestamp, value: h.weight      })), '#1B4332');
  } else {
    ['c-hr', 'c-spo2', 'c-temp', 'c-wt'].forEach((id) => {
      document.getElementById(id).parentElement.innerHTML = '<div class="center muted text-sm">Chart unavailable.</div>';
    });
  }
  const anomalies = history.filter(h =>
    (h.heartRate   != null && vitalsStatus('heartRate',   h.heartRate)   !== 'green') ||
    (h.spo2        != null && vitalsStatus('spo2',        h.spo2)        !== 'green') ||
    (h.temperature != null && vitalsStatus('temperature', h.temperature) !== 'green')
  ).slice(-8).reverse();

  const host = document.getElementById('anomalies');
  if (!anomalies.length) {
    host.innerHTML = `<div class="muted text-sm">No anomalies detected in this period.</div>`;
  } else {
    host.innerHTML = anomalies.map(a => {
      const issues = [];
      if (a.heartRate   != null && vitalsStatus('heartRate',   a.heartRate)   !== 'green') issues.push(`HR ${a.heartRate} bpm`);
      if (a.spo2        != null && vitalsStatus('spo2',        a.spo2)        !== 'green') issues.push(`SpO₂ ${a.spo2.toFixed(1)}%`);
      if (a.temperature != null && vitalsStatus('temperature', a.temperature) !== 'green') issues.push(`Temp ${a.temperature.toFixed(1)}°C`);
      return `<div class="list-item">
        <span class="dot dot-amber"></span>
        <div style="flex:1"><div style="font-weight:600">${issues.join(' · ')}</div>
        <div class="text-xs muted">${formatDate(a.timestamp)}</div></div>
      </div>`;
    }).join('');
  }
  document.getElementById('last-sync').textContent = 'Last synced ' + formatDate(new Date().toISOString());
}

document.getElementById('range').addEventListener('change', (e) => render(Number(e.target.value)));
document.getElementById('sync').addEventListener('click', () => { render(Number(document.getElementById('range').value)); toast('Device synced'); });
render(7);
