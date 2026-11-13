/* Service Worker – Wildtruhe
 * Bei JEDER Änderung an App-Dateien VERSION erhöhen (gleich wie APP_VERSION in index.html)
 * → die App merkt das beim Start / alle 30 Min. und installiert das Update.
 * Daten (data/…) und GitHub-API werden nie zwischengespeichert. */
const VERSION = 'wt-1.2.1';
const SHELL = ['./', 'index.html', 'manifest.json', 'icon-192.png', 'icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL.map(u => new Request(u, {cache:'reload'})))));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('message', e => { if (e.data === 'skipWaiting') self.skipWaiting(); });

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const u = new URL(e.request.url);
  if (u.origin !== location.origin || u.pathname.includes('/data/')) return;
  // App-Dateien aus dem Cache der aktuellen Version (schnell, offline) – neue Version kommt über das SW-Update
  e.respondWith(caches.open(VERSION).then(async c => {
    const hit = e.request.mode === 'navigate'
      ? (await c.match('index.html')) || (await c.match('./'))
      : await c.match(e.request, {ignoreSearch:true});
    if (hit) return hit;
    try { return await fetch(e.request); }
    catch(err) { return (await c.match('index.html')) || Response.error(); }
  }));
});
self.addEventListener('notificationclick', e => { e.notification.close(); e.waitUntil(clients.openWindow('./')); });
