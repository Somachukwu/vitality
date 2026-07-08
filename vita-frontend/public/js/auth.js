const BASE_URL = 'http://127.0.0.1:8000/api';

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

export async function registerApi(name, email, password, age, sex, goalType) {
  const goalMap = { lose_weight: 'weight_loss', gain_weight: 'weight_gain', maintain: 'maintenance', maintenance: 'maintenance', weight_loss: 'weight_loss', weight_gain: 'weight_gain' };
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name, email, password,
      age: age ? Number(age) : null,
      sex: sex || null,
      goal_type: goalMap[goalType] || 'maintenance',
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Registration failed');
  localStorage.setItem('token', data.access_token);
  saveUser({ id: data.user_id, name: data.name, email });
  return data;
}
