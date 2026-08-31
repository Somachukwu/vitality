import { BASE_URL } from './api.js';

export function getToken() { return localStorage.getItem('token'); }

export function getUser() {
  try { return JSON.parse(localStorage.getItem('user')) || {}; }
  catch { return {}; }
}

export function saveUser(u) { localStorage.setItem('user', JSON.stringify(u)); }

export function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.href = 'login.html';
}

export function requireAuth() {
  if (!getToken()) window.location.href = 'login.html';
}

export async function loginApi(email, password) {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Login failed');
  localStorage.setItem('token', data.access_token);
  saveUser({ id: data.user_id, name: data.name, email });
  return data;
}

export async function registerApi(name, email, password, age, sex, height, activityLevel, goalType) {
  const goalMap = { lose_weight: 'weight_loss', gain_weight: 'weight_gain', maintain: 'maintenance', maintenance: 'maintenance', weight_loss: 'weight_loss', weight_gain: 'weight_gain' };
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name, email, password,
      age: age ? Number(age) : null,
      sex: sex || 'male',
      height: height ? Number(height) : null,
      activity_level: activityLevel || 'moderate',
      goal_type: goalMap[goalType] || 'maintenance',
    }),
  });
  let data;
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok) {
    let msg = 'Registration failed';
    if (typeof data.detail === 'string') {
      msg = data.detail;
    } else if (Array.isArray(data.detail) && data.detail.length > 0) {
      msg = data.detail.map(d => d.msg || `${d.loc?.join('.')}: invalid`).join(', ');
    }
    throw new Error(msg);
  }
  localStorage.setItem('token', data.access_token);
  saveUser({ id: data.user_id, name: data.name, email });
  return data;
}
