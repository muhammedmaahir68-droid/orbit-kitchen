// Minimal service worker: caches the app shell so the app is installable and loads
// instantly on repeat visits. Live order/kitchen/menu data always goes to the network —
// this is a real-time system, so we deliberately do NOT cache API or WebSocket traffic.
const CACHE = "orbit-shell-v1";
const SHELL = ["/app/index.html", "/app/manifest.json", "/app/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Never cache API calls or WebSocket upgrades — always live.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
