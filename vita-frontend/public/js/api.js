const BASE_URL = 'http://127.0.0.1:8000/api';

async function request(endpoint, options = {}) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.href = 'login.html';
    return;
  }
  if (!res.ok) throw new Error(await res.text());
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get:    (url)       => request(url),
  post:   (url, body) => request(url, { method: 'POST',  body: JSON.stringify(body) }),
  put:    (url, body) => request(url, { method: 'PUT',   body: JSON.stringify(body) }),
  patch:  (url, body) => request(url, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: (url)       => request(url, { method: 'DELETE' }),
  postForm: (url, formData) =>
    fetch(`${BASE_URL}${url}`, {
      method: 'POST',
      body: formData,
      headers: localStorage.getItem('token')
        ? { Authorization: `Bearer ${localStorage.getItem('token')}` }
        : {},
    }).then((r) => r.json()),
};
