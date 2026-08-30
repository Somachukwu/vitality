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
    host.innerHTML = `<div class="card center muted">No insights recorded yet.</div>`;
    return;
  }
  host.innerHTML = list.map(r => {
    const m = TYPE_META[r.type] || TYPE_META.nutrition;
    let actionBtn = '';
    const rawRoute = r.action_data?.route || '';
    const cleanRoute = rawRoute.replace(/^\//, '');
    if (cleanRoute) {
      actionBtn = `<a href="${cleanRoute}" class="btn btn-ghost text-xs" style="text-decoration:none; font-weight:600">${r.action_data?.action_label || 'View'} →</a>`;
    }

    const tierBadge = r.tier === 'safety' ? '<span class="badge badge-critical">Safety Alert</span>' : '';

    return `<div class="card${r.is_read ? ' opacity-60' : ''}" style="${r.tier === 'safety' ? 'border-left:4px solid #ef4444' : ''}">
      <div class="row between mb-1">
        <div class="row gap-xs align-center">
          <span class="badge ${m.badge}"><i data-lucide="${m.icon}"></i> ${m.label}</span>
          ${tierBadge}
        </div>
        <span class="badge ${severityBadge(r.severity)}">${r.severity}</span>
      </div>
      ${r.title ? `<h3 style="margin: 0.35rem 0; font-size:1.05rem; font-weight:600">${r.title}</h3>` : ''}
      <p style="line-height:1.5">${r.message}</p>
      <div class="row between align-center mt-2">
        <span class="text-xs muted">${formatDate(r.created_at)}</span>
        <div class="row gap-sm align-center">
          ${actionBtn}
          ${r.is_read ? '<span class="text-xs muted">Read</span>' : `<button class="btn btn-ghost text-xs" onclick="markRead(${r.id})">Mark read</button>`}
        </div>
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
