/* Serviceflow service worker — caches the app shell for offline load.
   Strategy: same-origin GET → cache-first with background refresh;
   cross-origin (the API) and non-GET → straight to the network. */
const CACHE = "serviceflow-shell-v1";
const SHELL = [
  "/index.html",
  "/login.html",
  "/app/",
  "/app/index.html",
  "/portal/",
  "/portal/index.html",
  "/assets/css/design-system.css",
  "/assets/js/api.js",
  "/assets/js/ui.js",
  "/assets/js/staff.js",
  "/assets/js/portal.js",
  "/assets/img/favicon.svg",
  "/assets/img/icon-192.png",
  "/assets/img/icon-512.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // Only handle same-origin GETs; let API calls and others hit the network.
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
