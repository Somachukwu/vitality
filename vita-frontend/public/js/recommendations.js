import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { formatDate, initLucide, applyStoredTheme, initThemeToggle } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('recommendations.html');
initThemeToggle();

const TYPE_META = {
  nutrition:     { label: 'Nutritional tip',  icon: 'apple',        badge: 'badge-success' },
  activity:      { label: 'Activity alert',   icon: 'footprints',   badge: 'badge-info' },
  health_alert:  { label: 'Health warning',   icon: 'shield-alert', badge: 'badge-warning' },
  goal_progress: { label: 'Goal progress',    icon: 'target',       badge: 'badge-info' },
};

function severityBadge(s) {
  if (s === 'critical') return 'badge-critical';
  if (s === 'warning')  return 'badge-warning';
  return 'badge-info';
}

let allRecs = [];

async function load() {
  try {
    allRecs = await api.get('/recommendations/');
  } catch {
    allRecs = [];
  }
  render();
}

function render() {
  const filter = document.getElementById('type-filter').value;
  const list = allRecs.filter(r => !filter || r.type === filter);
  const host = document.getElementById('list');
  if (!list.length) {
    host.innerHTML = `<div class="card center muted">No recommendations yet.</div>`;
    return;
  }
  host.innerHTML = list.map(r => {
    const m = TYPE_META[r.type] || TYPE_META.nutrition;
    return `<div class="card${r.is_read ? ' opacity-60' : ''}">
      <div class="row between mb-1">
        <span class="badge ${m.badge}"><i data-lucide="${m.icon}"></i> ${m.label}</span>
        <span class="badge ${severityBadge(r.severity)}">${r.severity}</span>
      </div>
      <p>${r.message}</p>
      <div class="row between mt-2">
        <span class="text-xs muted">${formatDate(r.created_at)}</span>
        ${r.is_read ? '<span class="text-xs muted">Read</span>' : `<button class="btn btn-ghost text-xs" onclick="markRead(${r.id})">Mark as read</button>`}
      </div>
    </div>`;
  }).join('');
  initLucide();
}

window.markRead = async (id) => {
  try {
    await api.patch(`/recommendations/${id}/read`);
    const rec = allRecs.find(r => r.id === id);
    if (rec) rec.is_read = true;
    render();
  } catch { /* ignore */ }
};

document.getElementById('type-filter').addEventListener('change', render);
load();
