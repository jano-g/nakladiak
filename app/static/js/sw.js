/* Nakladiak service worker: cache only /static/ (network first, cache as offline fallback).
   HTML, API and /p/ pages always come from the network. JS/CSS carry ?v=N, so a cache lookup
   must never ignore the query string (that kept returning stale files forever in kal). */
const VERSION = 'nakladiak-v1';
const STATIC = ['/static/css/app.css', '/static/js/app.js', '/static/img/icon-192.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(STATIC.map((u) => new Request(u, { cache: 'reload' }))).catch(() => null)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) caches.open(VERSION).then((c) => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.open(VERSION).then((c) => c.match(e.request))));
  }
});
