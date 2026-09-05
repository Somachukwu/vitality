import { requireAuth } from './auth.js';
import { renderNav } from './nav.js';
import { initLucide, applyStoredTheme, initThemeToggle } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('recommendations.html');
initThemeToggle();

const TYPE_META = {
  nutrition:     { label: 'Nutrition',       icon: 'apple',        badge: 'badge-success' },
  activity:      { label: 'Activity',        icon: 'footprints',   badge: 'badge-info' },
  health_alert:  { label: 'Health Warning',  icon: 'shield-alert', badge: 'badge-warning' },
  goal_progress: { label: 'Goal Progress',   icon: 'target',       badge: 'badge-info' },
};

function getRecBadgeInfo(r) {
  if (r.rule_id === 'dynamic.morning_poetic') {
    return { label: 'Morning Vitality', icon: 'sun', badgeClass: 'badge-success' };
  }
  if (r.rule_id?.startsWith('milestone.')) {
    return { label: 'Milestone', icon: 'sparkles', badgeClass: 'badge-info' };
  }
  if (r.rule_id?.startsWith('time.morning_low_steps') || r.rule_id?.startsWith('time.evening_steps')) {
    return { label: 'Activity Check', icon: 'footprints', badgeClass: 'badge-info' };
  }
  if (r.rule_id?.startsWith('time.midday_meal') || r.rule_id?.startsWith('time.afternoon_meal')) {
    return { label: 'Meal Check-In', icon: 'apple', badgeClass: 'badge-success' };
  }
  if (r.rule_id?.startsWith('time.evening_')) {
    return { label: 'Calorie Guidance', icon: 'target', badgeClass: 'badge-success' };
  }
  if (r.rule_id?.startsWith('sleep.')) {
    return { label: 'Sleep & Recovery', icon: 'moon', badgeClass: 'badge-info' };
  }
  const m = TYPE_META[r.type] || TYPE_META.nutrition;
  return { label: m.label, icon: m.icon, badgeClass: m.badge };
}

function severityBadge(s) {
  if (s === 'critical') return 'badge-critical';
  if (s === 'warning')  return 'badge-warning';
  return 'badge-info';
}

// Date grouping helper
function getDateGroup(dateStr) {
  const now = new Date();
  const d = new Date(dateStr);
  const todayStr = now.toDateString();
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === todayStr) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  const daysDiff = Math.floor((now - d) / 864e5);
  if (daysDiff < 7) return 'This Week';
  return 'This Month'; // everything older than 7 days — no separate "Earlier" bucket
}

function formatRelativeTime(dateStr) {
  const now = new Date();
  const d = new Date(dateStr);
  const diffMs = now - d;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHrs = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHrs / 24);
  if (diffMins < 2) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  // Within 24 hours — show the exact trigger time (e.g. "9:47 AM")
  if (diffHrs < 24) return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

let allRecs = [];

async function load() {
  const host = document.getElementById('list');
  if (host) host.innerHTML = `
    <div class="card" style="opacity:0.5">
      <div style="height:16px; background:var(--border); border-radius:8px; width:40%; margin-bottom:0.75rem"></div>
      <div style="height:12px; background:var(--border); border-radius:6px; width:90%; margin-bottom:0.5rem"></div>
      <div style="height:12px; background:var(--border); border-radius:6px; width:75%"></div>
    </div>
    <div class="card" style="opacity:0.3">
      <div style="height:16px; background:var(--border); border-radius:8px; width:55%; margin-bottom:0.75rem"></div>
      <div style="height:12px; background:var(--border); border-radius:6px; width:85%"></div>
    </div>
  `;
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

  const unreadCount = list.filter(r => !r.is_read).length;

  if (!list.length) {
    host.innerHTML = `
      <div class="card center" style="padding:2.5rem 1.5rem; text-align:center">
        <i data-lucide="sparkles" style="width:40px; height:40px; color:var(--teal); margin-bottom:1rem"></i>
        <h3 style="margin-bottom:0.5rem">No insights yet</h3>
        <p class="muted text-sm" style="max-width:280px; margin:0 auto 1.25rem">
          Your daily health insights will appear here as you use the app. Start by visiting the dashboard.
        </p>
        <a href="dashboard.html" class="btn btn-primary text-sm" style="text-decoration:none">Go to Dashboard</a>
      </div>
    `;
    initLucide();
    return;
  }

  // Group by date
  const groups = {};
  const groupOrder = ['Today', 'Yesterday', 'This Week', 'This Month'];
  list.forEach(r => {
    const g = getDateGroup(r.created_at);
    if (!groups[g]) groups[g] = [];
    groups[g].push(r);
  });

  let html = '';

  // Mark all read button
  if (unreadCount > 0) {
    html += `<div class="row" style="justify-content:flex-end; margin-bottom:0.5rem">
      <button class="btn btn-ghost text-xs" onclick="markAllRead()" style="font-weight:600">
        <i data-lucide="check-check" style="width:13px;height:13px;margin-right:4px"></i>Mark all read
      </button>
    </div>`;
  }

  groupOrder.forEach(groupName => {
    if (!groups[groupName]) return;
    html += `<div class="text-xs" style="font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); margin:1rem 0 0.4rem">${groupName}</div>`;
    groups[groupName].forEach(r => {
      const badgeInfo = getRecBadgeInfo(r);
      let actionBtn = '';
      const rawRoute = r.action_data?.route || '';
      const cleanRoute = rawRoute.replace(/^\//, '');
      if (cleanRoute) {
        actionBtn = `<a href="${cleanRoute}" class="btn btn-ghost text-xs" style="text-decoration:none; font-weight:600">${r.action_data?.action_label || 'View'} →</a>`;
      }
      const tierBadge = r.tier === 'safety' ? '<span class="badge badge-critical">Safety Alert</span>' : '';
      html += `
        <div class="card${r.is_read ? ' opacity-60' : ''}" style="${r.tier === 'safety' ? 'border-left:4px solid #ef4444' : ''}">
          <div class="row between mb-1 flex-wrap align-center">
            <div class="row gap-xs align-center" style="flex-wrap:wrap; gap:0.35rem">
              <span class="badge ${badgeInfo.badgeClass}"><i data-lucide="${badgeInfo.icon}"></i> ${badgeInfo.label}</span>
              ${tierBadge}
              ${r.severity !== 'info' ? `<span class="badge ${severityBadge(r.severity)}">${r.severity}</span>` : ''}
            </div>
            <span class="text-xs muted" style="white-space:nowrap">${formatRelativeTime(r.created_at)}</span>
          </div>
          ${r.title ? `<h3 style="margin:0.35rem 0 0.25rem; font-size:1rem; font-weight:600">${r.title}</h3>` : ''}
          <p style="line-height:1.55; font-size:0.9rem">${r.message}</p>
          <div class="row between align-center mt-2 rec-footer">
            <div class="row gap-sm align-center flex-wrap rec-actions">
              ${actionBtn}
              ${r.is_read ? '' : `<button class="btn btn-ghost text-xs" onclick="markRead(${r.id})">Mark read</button>`}
            </div>
          </div>
        </div>
      `;
    });
  });

  host.innerHTML = html;
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

window.markAllRead = async () => {
  const unread = allRecs.filter(r => !r.is_read);
  await Promise.all(unread.map(r =>
    api.patch(`/recommendations/${r.id}/read`).then(() => { r.is_read = true; }).catch(() => {})
  ));
  render();
};

document.getElementById('type-filter')?.addEventListener('change', render);
load();


