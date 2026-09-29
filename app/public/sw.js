const CACHE_NAME = "unde-locuiesc-v3";
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

  // Doar http(s). Extensiile de browser fac cereri chrome-extension:// (blob:, data: etc.)
  // care nu pot fi puse în Cache API — aruncau „Request scheme … unsupported". Le lăsăm
  // complet în seama browserului (fără respondWith).
  if (!request.url.startsWith("http")) return;

  const url = new URL(request.url);

  // Navigare (documentul HTML): NETWORK-FIRST. Cererea „/" nu se termină în .html și cădea
  // pe ramura cache-first de mai jos → la un deploy nou servea un index.html vechi care
  // trimitea spre un bundle cu hash vechi, inexistent pe server → fallback SPA (text/html)
  // în locul JS-ului → „Failed to load module script" → pagină albă. Network-first ține
  // index.html mereu proaspăt (cu hash-ul curent); offline cădem pe copia din cache.
  if (request.mode === "navigate") {
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
          caches.match(request).then((cached) => cached || caches.match("/index.html"))
        )
    );
    return;
  }

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

  // HTML/JS/CSS/MD: network-first (documentatie.md se editează → nu trebuie servit vechi)
  if (
    url.pathname.endsWith(".html") ||
    url.pathname.endsWith(".js") ||
    url.pathname.endsWith(".css") ||
    url.pathname.endsWith(".md")
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
