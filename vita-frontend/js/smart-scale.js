import { requireAuth, getUser, saveUser } from './auth.js';
import { renderNav } from './nav.js';
import { applyStoredTheme, initThemeToggle, initLucide, toast, formatTime } from './utils.js';
import { api } from './api.js';

applyStoredTheme();
requireAuth();
renderNav('smart-scale.html');
initThemeToggle();

let user = getUser();
let currentWeight = null;
let lastSeenReadingTimestamp = null;
let pollInterval = null;
const sessionReadings = [];

// DOM Elements
const statusBadge = document.getElementById('scale-status-badge');
const deviceNameEl = document.getElementById('scale-device-name');
const lastSeenEl = document.getElementById('scale-last-seen');


const gaugeEl = document.getElementById('scale-gauge');
const weightDisplayEl = document.getElementById('live-weight-display');
const readingStatusEl = document.getElementById('scale-reading-status');
const btnLogWeight = document.getElementById('btn-log-weight');
const btnWeightNum = document.getElementById('btn-weight-num');

const curLoggedVal = document.getElementById('cur-logged-val');
const streamListEl = document.getElementById('readings-stream-list');
const emptyStreamMsg = document.getElementById('empty-stream-msg');
const btnClearReadings = document.getElementById('btn-clear-readings');

const manualForm = document.getElementById('manual-weight-form');
const manualInput = document.getElementById('manual-weight-input');
const btnManualSubmit = document.getElementById('btn-manual-submit');

// Render initial user weight from cache if available
if (user && user.weight != null) {
  curLoggedVal.textContent = `${Number(user.weight).toFixed(1)} kg`;
}

// Backend stores UTC without 'Z' — append it so JS parses correctly
function parseServerDate(str) {
  if (!str) return null;
  return new Date(str.endsWith('Z') || str.includes('+') ? str : str + 'Z');
}

// Availability threshold matching profile.js (90 seconds)
const ONLINE_THRESHOLD_MS = 90 * 1000;
function isOnline(lastSeenStr) {
  const lastSeen = parseServerDate(lastSeenStr);
  if (!lastSeen) return false;
  return (Date.now() - lastSeen.getTime()) < ONLINE_THRESHOLD_MS;
}

function formatDeviceTime(value) {
  const d = parseServerDate(value);
  if (!d) return 'Never synced';
  return 'Last sync: ' + d.toLocaleString();
}

function updateConnectionStatus(data) {
  const statusBadgeHost = document.getElementById('scale-status-badge');

  if (!data.device_registered) {
    if (statusBadgeHost) {
      statusBadgeHost.innerHTML = '<span class="badge badge-warning">&#9679; Not paired</span>';
    }
    deviceNameEl.textContent = 'Smart Scale (Not paired)';
    lastSeenEl.textContent = 'Last sync: Never synced';
    if (!currentWeight) {
      readingStatusEl.textContent = 'No smart scale paired · Pair your scale in Profile or enter weight manually';
    }
  } else {
    // Availability strictly mirrors profile scale card logic
    const online = isOnline(data.last_seen);

    if (statusBadgeHost) {
      statusBadgeHost.innerHTML = online
        ? '<span class="badge badge-success">&#9679; Online</span>'
        : '<span class="badge badge-warning" style="color:#b91c1c">&#9679; Offline</span>';
    }

    const uidDesc = data.device_uid ? ` (${data.device_uid})` : '';
    deviceNameEl.textContent = `${data.device_name || 'Smart Scale'}${uidDesc}`;
    lastSeenEl.textContent = formatDeviceTime(data.last_seen);

    if (online) {
      if (!currentWeight) {
        readingStatusEl.textContent = 'Scale is online · Step on the scale to start measuring';
      }
    } else {
      if (!currentWeight) {
        readingStatusEl.textContent = 'Scale is offline · Connect to Wi-Fi or enter weight manually below';
      }
    }
  }

  if (data.current_logged_weight != null) {
    curLoggedVal.textContent = `${Number(data.current_logged_weight).toFixed(1)} kg`;
    if (user && user.weight !== data.current_logged_weight) {
      user.weight = data.current_logged_weight;
      saveUser(user);
    }
  }
}


function handleNewReading(reading) {
  if (!reading || reading.weight == null) return;

  currentWeight = Number(reading.weight);
  weightDisplayEl.textContent = currentWeight.toFixed(1);
  btnWeightNum.textContent = currentWeight.toFixed(1);
  btnLogWeight.disabled = false;
  gaugeEl.classList.add('active-reading');
  readingStatusEl.textContent = 'Steady reading received · Click "Add to log" to record';

  // Check if this reading timestamp is already in our session list
  const rTime = reading.recorded_at || reading.received_at;
  const isDuplicate = sessionReadings.some(r => r.time === rTime && r.weight === currentWeight);

  if (!isDuplicate) {
    sessionReadings.unshift({
      weight: currentWeight,
      time: rTime,
      displayTime: formatTime(rTime),
    });
    renderSessionStream();
  }
}

function renderSessionStream() {
  if (!sessionReadings.length) {
    emptyStreamMsg.style.display = 'block';
    return;
  }
  emptyStreamMsg.style.display = 'none';

  streamListEl.innerHTML = sessionReadings.map((item, idx) => `
    <div class="reading-stream-item">
      <div>
        <div style="font-weight:700; font-size:1.15rem" class="num">${item.weight.toFixed(1)} <span class="text-xs muted" style="font-weight:400">kg</span></div>
        <div class="text-xs muted">${item.displayTime}</div>
      </div>
      <button class="btn btn-ghost text-xs btn-stream-log" data-weight="${item.weight}" style="padding:0.35rem 0.75rem; border-color:var(--teal); color:var(--teal-600); font-weight:600">
        Log this
      </button>
    </div>
  `).join('');

  // Attach quick log handlers
  streamListEl.querySelectorAll('.btn-stream-log').forEach(btn => {
    btn.addEventListener('click', () => {
      const wt = Number(btn.getAttribute('data-weight'));
      if (wt > 0) logWeightToDatabase(wt, btn);
    });
  });
}

async function fetchLiveScale() {
  try {
    const data = await api.get('/vitals/scale/live');
    if (!data) return;

    updateConnectionStatus(data);

    if (data.latest_reading) {
      const ts = data.latest_reading.recorded_at || data.latest_reading.received_at;
      if (ts !== lastSeenReadingTimestamp) {
        lastSeenReadingTimestamp = ts;
        handleNewReading(data.latest_reading);
      }
    }
  } catch (err) {
    console.warn('Failed to poll scale live endpoint:', err);
  }
}

async function logWeightToDatabase(weight, triggerBtn = null) {
  if (!weight || isNaN(weight) || weight <= 0) {
    toast('Please enter a valid weight', 'error');
    return;
  }

  const btn = triggerBtn || btnLogWeight;
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="width:16px; height:16px; border-width:2px; margin:0; display:inline-block"></span> Saving…';

  try {
    const res = await api.post('/vitals/scale/log', { weight });
    toast(`Weight successfully logged: ${weight.toFixed(1)} kg`, 'success');

    // Update state & UI
    curLoggedVal.textContent = `${weight.toFixed(1)} kg`;
    user = getUser();
    if (user) {
      user.weight = weight;
      saveUser(user);
    }

    btn.innerHTML = '<i data-lucide="check"></i> Logged!';
    initLucide();
    setTimeout(() => {
      btn.disabled = false;
      btn.innerHTML = origHtml;
      initLucide();
    }, 2000);
  } catch (err) {
    toast(`Failed to log weight: ${err.message || 'Server error'}`, 'error');
    btn.disabled = false;
    btn.innerHTML = origHtml;
    initLucide();
  }
}

// Event Listeners
btnLogWeight.addEventListener('click', () => {
  if (currentWeight != null) {
    logWeightToDatabase(currentWeight, btnLogWeight);
  }
});

manualForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const val = Number(manualInput.value);
  if (!val || isNaN(val) || val <= 0) return;

  await logWeightToDatabase(val, btnManualSubmit);
  manualInput.value = '';
});

btnClearReadings.addEventListener('click', () => {
  sessionReadings.length = 0;
  streamListEl.innerHTML = '';
  streamListEl.appendChild(emptyStreamMsg);
  emptyStreamMsg.style.display = 'block';
});

// Initial load & Polling
fetchLiveScale();
pollInterval = setInterval(fetchLiveScale, 2000);

window.addEventListener('beforeunload', () => {
  if (pollInterval) clearInterval(pollInterval);
});

initLucide();

