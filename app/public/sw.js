const CACHE_NAME = "unde-locuiesc-v2";
const ASSETS = [
  "/",
  "/index.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS).catch(() => {
        // OK dacă nu toți assets sunt disponibili la install
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // POST/PUT/DELETE: mereu network-first
  if (request.method !== "GET") {
    event.respondWith(
      fetch(request).catch(() => {
        return new Response("Offline", { status: 503 });
      })
    );
    return;
  }

  // Date publicate (parquet/geojson/registry): NETWORK-FIRST. Numele fișierelor sunt
  // stabile, dar conținutul se schimbă la re-export — cache-only servea o schemă veche la
  // infinit (ex. env.parquet fără coloane noi → „column not found"). fetch() respectă
  // HTTP cache (max-age), deci rămâne rapid; păstrăm o copie a răspunsurilor 200 pentru offline.
  if (url.pathname.includes("/data/") && !url.pathname.includes("/live/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then(
            (cached) => cached || new Response("Offline — date indisponibile", { status: 503 })
          )
        )
    );
    return;
  }

  // Live data: network-first cu cache fallback
  if (url.pathname.includes("/live/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (!response || response.status !== 200) return response;
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, clone);
          });
          return response;
        })
        .catch(() => {
          return caches.match(request).then((cached) => {
            return cached || new Response("Offline — live data unavailable", { status: 503 });
          });
        })
    );
    return;
  }

  // HTML/JS/CSS: network-first
  if (
    url.pathname.endsWith(".html") ||
    url.pathname.endsWith(".js") ||
    url.pathname.endsWith(".css")
  ) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (!response || response.status !== 200) return response;
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, clone);
          });
          return response;
        })
        .catch(() => {
          return caches.match(request);
        })
    );
    return;
  }

  // Default: cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      return cached || fetch(request);
    })
  );
});
