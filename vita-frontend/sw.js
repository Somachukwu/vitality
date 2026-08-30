// Vitality Service Worker — Caches core shell assets for instant load and offline resilience
const CACHE_NAME = 'vitality-shell-v1';
const CORE_ASSETS = [
  '/',
  '/dashboard.html',
  '/vitals.html',
  '/food-log.html',
  '/profile.html',
  '/recommendations.html',
  '/login.html',
  '/register.html',
  '/styles/main.css',
  '/js/api.js',
  '/js/utils.js',
  '/js/dashboard.js',
  '/js/vitals.js',
  '/js/food-log.js',
  '/js/profile.js',
  '/js/recommendations.js',
  '/vitality-logo.png',
  '/vitality-logo-icon.png',
  '/vitality-favicon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(CORE_ASSETS).catch((err) => {
        console.warn('[ServiceWorker] Some assets failed to pre-cache:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API, auth, or backend requests
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/auth') || url.port === '8000') {
    return;
  }

  // Network-first for HTML navigation, cache-first for static CSS/JS/images
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      });
    })
  );
});