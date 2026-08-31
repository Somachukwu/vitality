import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { formatDate, initLucide, applyStoredTheme, initThemeToggle } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('recommendations.html');
initThemeToggle();

const TYPE_META = {
  nutrition:     { label: 'Nutrition',      icon: 'apple',        badge: 'badge-success' },
  activity:      { label: 'Activity',       icon: 'footprints',   badge: 'badge-info' },
  health_alert:  { label: 'Health Alert',   icon: 'shield-alert', badge: 'badge-warning' },
  goal_progress: { label: 'Goal Progress',  icon: 'target',       badge: 'badge-info' },
};

function severityBadge(s) {
  if (s === 'critical') return '<span class="badge badge-critical">Critical</span>';
  if (s === 'warning')  return '<span class="badge badge-warning">Important</span>';
  return '';
}

function tierBadge(tier) {
  if (tier === 'safety') return '<span class="badge badge-critical"><i data-lucide="alert-triangle"></i> Safety Alert</span>';
  if (tier === 'primary_action') return '<span class="badge badge-primary-tier"><i data-lucide="zap"></i> Key Action</span>';
  return '';
}

let allRecs = [];

async function load() {
  const host = document.getElementById('list');
  try {
    allRecs = await api.get('/recommendations/');
  } catch {
    allRecs = [];
  }
  render();
}

function render() {
  const filter = document.getElementById('type-filter')?.value || '';
  const list = allRecs.filter(r => !filter || r.type === filter);
  const host = document.getElementById('list');
  if (!host) return;

  if (!list.length) {
    host.innerHTML = `
      <div class="card center muted" style="padding: 3rem 1.5rem; border-radius: 16px;">
        <div style="width: 56px; height: 56px; border-radius: 50%; background: var(--green-50); color: var(--teal); display: grid; place-items: center; margin: 0 auto 1rem; font-size: 1.5rem;">
          <i data-lucide="sparkles"></i>
        </div>
        <h3 style="color: var(--text); margin-bottom: 0.5rem; font-size: 1.125rem;">All caught up!</h3>
        <p class="text-sm" style="max-width: 400px; margin: 0 auto 1.25rem;">
          No active insights right now. Log your daily meals or sync your vitals to generate fresh, personalized recommendations.
        </p>
        <div class="row gap-sm" style="justify-content: center; flex-wrap: wrap;">
          <a href="food-log.html" class="btn btn-accent text-sm"><i data-lucide="camera"></i> Log a meal</a>
          <a href="goals.html" class="btn btn-ghost text-sm"><i data-lucide="target"></i> View targets</a>
        </div>
      </div>
    `;
    initLucide();
    return;
  }

  host.innerHTML = list.map(r => {
    const m = TYPE_META[r.type] || TYPE_META.nutrition;
    const isSafety = r.tier === 'safety';
    const isPrimary = r.tier === 'primary_action';

    let actionBtn = '';
    const rawRoute = r.action_data?.route || '';
    const cleanRoute = rawRoute.replace(/^\//, '');
    if (cleanRoute) {
      const btnClass = isPrimary ? 'btn btn-accent text-xs' : 'btn btn-ghost text-xs';
      actionBtn = `<a href="${cleanRoute}" class="${btnClass}" style="text-decoration:none; font-weight:700; border-radius:999px;">${r.action_data?.action_label || 'View'} →</a>`;
    }

    const cardClass = [
      'card',
      'insight-card',
      r.is_read ? 'opacity-70' : '',
      isSafety ? 'insight-safety' : '',
      isPrimary && !r.is_read ? 'insight-primary' : '',
    ].filter(Boolean).join(' ');

    return `
      <article class="${cardClass}">
        <div class="insight-card-header mb-1">
          <div class="row gap-xs flex-wrap align-center">
            <span class="badge ${m.badge}"><i data-lucide="${m.icon}"></i> ${m.label}</span>
            ${tierBadge(r.tier)}
            ${severityBadge(r.severity)}
          </div>
          ${r.is_read ? '<span class="badge badge-read text-xs">Read</span>' : ''}
        </div>

        ${r.title ? `<h3 class="insight-title">${r.title}</h3>` : ''}
        <p class="insight-body">${r.message}</p>

        <div class="insight-footer mt-2">
          <span class="text-xs muted row gap-xs align-center">
            <i data-lucide="clock" style="width:13px; height:13px"></i>
            ${formatDate(r.created_at)}
          </span>
          <div class="row gap-xs align-center flex-wrap insight-actions">
            ${actionBtn}
            ${!r.is_read ? `<button class="btn btn-ghost text-xs mark-read-btn" onclick="markRead(${r.id})">Mark read</button>` : ''}
          </div>
        </div>
      </article>
    `;
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

document.getElementById('type-filter')?.addEventListener('change', render);
load();
