import { requireAuth, logout } from './auth.js';
import { renderNav } from './nav.js';
import { toast, applyStoredTheme, initThemeToggle, initLucide } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('profile.html');
initThemeToggle();

const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v ?? ''; };
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}[ch]));

let profile = {};
let devices = [];

async function loadProfile() {
  try {
    profile = await api.get('/users/profile');
    set('name',      profile.name);
    set('email',     profile.email);
    set('age',       profile.age);
    set('sex',       profile.sex);
    set('heightCm',  profile.height);
    set('weightKg',  profile.weight);
    set('cal',       profile.daily_calorie_target);
    set('goal',      profile.goal_type);
    set('diet',      (profile.dietary_restrictions || []).join(', '));
    const notifPref = profile.notification_preferences || {};
    const pushEl  = document.getElementById('notif-push');
    const emailEl = document.getElementById('notif-email');
    if (pushEl)  pushEl.checked  = notifPref.push  !== false;
    if (emailEl) emailEl.checked = !!notifPref.email;
  } catch {
    toast('Could not load profile.', 'error');
  }
}

const editableFields = () => document.querySelectorAll('#profile-form input:not(#email), #profile-form select');
let snapshot = {};

function captureSnapshot() { editableFields().forEach(f => { snapshot[f.id] = f.value; }); }
function restoreSnapshot() { editableFields().forEach(f => { if (f.id in snapshot) f.value = snapshot[f.id]; }); }

function setEditMode(editing) {
  const form = document.getElementById('profile-form');
  editableFields().forEach(f => { f.disabled = !editing; });
  form.classList.toggle('profile-readonly', !editing);
  document.getElementById('edit-btn').classList.toggle('hidden', editing);
  document.getElementById('form-actions').classList.toggle('hidden', !editing);
  if (editing) initLucide();
}

setEditMode(false);
loadProfile();
loadDevices();

document.getElementById('edit-btn').addEventListener('click', () => { captureSnapshot(); setEditMode(true); });
document.getElementById('cancel-btn').addEventListener('click', () => { restoreSnapshot(); setEditMode(false); });

document.getElementById('profile-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const get = (id) => document.getElementById(id)?.value ?? '';
  const btn = document.getElementById('save-btn') || e.submitter;
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const payload = {
      name:                    get('name').trim() || undefined,
      age:                     Number(get('age')) || undefined,
      sex:                     get('sex') || undefined,
      height:                  Number(get('heightCm')) || undefined,
      weight:                  Number(get('weightKg')) || undefined,
      daily_calorie_target:    Number(get('cal')) || undefined,
      goal_type:               get('goal') || undefined,
      dietary_restrictions:    get('diet').split(',').map(s => s.trim()).filter(Boolean),
      notification_preferences: {
        push:  document.getElementById('notif-push')?.checked  ?? true,
        email: document.getElementById('notif-email')?.checked ?? false,
      },
    };
    profile = await api.put('/users/profile', payload);
    setEditMode(false);
    toast('Profile updated');
  } catch (err) {
    toast('Could not save: ' + err.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Save changes'; }
  }
});

// Backend stores UTC without 'Z' — append it so JS parses correctly
function parseServerDate(str) {
  if (!str) return null;
  return new Date(str.endsWith('Z') || str.includes('+') ? str : str + 'Z');
}

// Device is Online if we heard from it within 3x its expected POST interval (90 s)
const ONLINE_THRESHOLD_MS = 90 * 1000;
function isOnline(device) {
  const lastSeen = parseServerDate(device.last_seen);
  if (!lastSeen) return false;
  return (Date.now() - lastSeen.getTime()) < ONLINE_THRESHOLD_MS;
}

function formatDeviceTime(value) {
  const d = parseServerDate(value);
  if (!d) return 'Never synced';
  return 'Last sync: ' + d.toLocaleString();
}

function deviceIcon(type) {
  return type === 'station' ? 'cpu' : 'watch';
}

function renderDevices() {
  const host = document.getElementById('devices-list');
  if (!devices.length) {
    host.innerHTML = '<div class="list-item muted">No devices connected yet.</div>';
    return;
  }

  host.innerHTML = devices.map((device) => {
    const online = isOnline(device);
    const onlineBadge = online
      ? '<span class="badge badge-success">● Online</span>'
      : '<span class="badge badge-warning" style="color:#b91c1c">● Offline</span>';

    return `
    <div class="list-item">
      <i data-lucide="${deviceIcon(device.device_type)}"></i>
      <div style="flex:1; min-width:0">
        <strong>${escapeHtml(device.device_name)}</strong>
        <div class="text-xs muted">${escapeHtml(device.device_uid)} · ${device.device_type}</div>
        <div class="text-xs muted">${formatDeviceTime(device.last_seen)}</div>
      </div>
      <div class="row gap-sm flex-wrap" style="justify-content:flex-end; align-items:center">
        ${onlineBadge}
        <span class="badge ${device.is_active ? 'badge-success' : 'badge-warning'}">${device.is_active ? 'Active' : 'Inactive'}</span>
        <button class="btn btn-ghost text-xs" type="button" data-device-key="${device.id}">API key</button>
        <button class="btn btn-ghost text-xs" type="button" data-device-delete="${device.id}" style="color:#b91c1c">Delete</button>
      </div>
    </div>`;
  }).join('');
  initLucide();
}

async function loadDevices() {
  try {
    devices = await api.get('/devices/');
  } catch {
    devices = [];
    toast('Could not load devices.', 'error');
  }
  renderDevices();
}

function hideDeviceForm() {
  document.getElementById('device-form').classList.add('hidden');
  document.getElementById('device-form').reset();
}

document.getElementById('add-device-btn').addEventListener('click', () => {
  const form = document.getElementById('device-form');
  form.classList.toggle('hidden');
  document.getElementById('device-key').classList.add('hidden');
  if (!form.classList.contains('hidden')) document.getElementById('device-name').focus();
});

document.getElementById('cancel-device-btn').addEventListener('click', hideDeviceForm);

document.getElementById('device-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('save-device-btn');
  const name = document.getElementById('device-name').value.trim();
  const uid = document.getElementById('device-uid').value.trim();
  if (!name || !uid) return;

  const deviceType = document.getElementById('device-type').value;
  btn.disabled = true;
  btn.textContent = 'Registering...';
  try {
    const device = await api.post('/devices/register', {
      device_name: name,
      device_uid: uid,
      device_type: deviceType,
    });
    document.getElementById('device-key').classList.remove('hidden');
    document.getElementById('device-key').innerHTML = `
      <div class="card-title">Device API key</div>
      <p class="text-sm muted mb-1">Use this key in the ESP32 firmware config.</p>
      <div class="mono text-sm" style="overflow-wrap:anywhere">${escapeHtml(device.api_key)}</div>
    `;
    hideDeviceForm();
    await loadDevices();
    toast('Device registered');
  } catch (err) {
    toast('Could not register device: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Register device';
  }
});

document.getElementById('devices-list').addEventListener('click', async (e) => {
  const keyBtn = e.target.closest('[data-device-key]');
  if (keyBtn) {
    const device = devices.find((d) => String(d.id) === keyBtn.dataset.deviceKey);
    if (!device) return;
    document.getElementById('device-key').classList.remove('hidden');
    document.getElementById('device-key').innerHTML = `
      <div class="card-title">Device API key</div>
      <p class="text-sm muted mb-1">Use this key in the ESP32 firmware config.</p>
      <div class="mono text-sm" style="overflow-wrap:anywhere">${escapeHtml(device.api_key)}</div>
    `;
    return;
  }

  const btn = e.target.closest('[data-device-delete]');
  if (!btn) return;
  if (!confirm('Permanently delete this device? Its historical vitals data will be kept, but the device will need to be re-registered.')) return;
  btn.disabled = true;
  btn.textContent = 'Deleting…';
  try {
    await api.delete(`/devices/${btn.dataset.deviceDelete}`);
    await loadDevices();
    toast('Device deleted');
  } catch (err) {
    toast('Could not delete device: ' + err.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Delete';
  }
});

document.getElementById('change-pw').addEventListener('click', () => toast('Password reset coming soon.'));
document.getElementById('logout-btn').addEventListener('click', logout);
