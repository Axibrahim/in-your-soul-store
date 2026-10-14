/*
 * IN YOUR SOUL service worker.
 *
 * Deliberately conservative. Pages are NEVER cached: every page carries the visitor's CSRF token,
 * login state and cart, so serving a stored copy would break forms and could show someone else's data.
 *
 *   - page navigations      network first; if the network is down show /offline
 *   - /static/* files       stale-while-revalidate (instant repeat loads, refreshed in the background)
 *   - everything else       untouched (POST/cart/checkout, Supabase images, Google Fonts, video ranges)
 *
 * Bump VERSION when this file changes in a way that needs old caches wiped.
 */
const VERSION = 'v1';
const CACHE = `iys-static-${VERSION}`;
const OFFLINE_URL = '/offline';
const PRECACHE = [OFFLINE_URL, '/static/images/icons/icon-192.png'];
const MAX_ENTRIES = 150;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(PRECACHE.map((url) => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n.startsWith('iys-') && n !== CACHE).map((n) => caches.delete(n)));
    if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
    await self.clients.claim();
  })());
});

async function trim(cache) {
  const keys = (await cache.keys()).filter((r) => !PRECACHE.includes(new URL(r.url).pathname));
  for (const key of keys.slice(0, Math.max(0, keys.length - MAX_ENTRIES))) await cache.delete(key);
}

async function navigate(event) {
  try {
    const preloaded = await event.preloadResponse;
    return preloaded || await fetch(event.request);
  } catch (err) {
    const cache = await caches.open(CACHE);
    return (await cache.match(OFFLINE_URL)) || Response.error();
  }
}

async function staleWhileRevalidate(event) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(event.request);
  const refresh = fetch(event.request)
    .then(async (res) => {
      if (res && res.ok && res.type === 'basic') {
        await cache.put(event.request, res.clone());
        await trim(cache);
      }
      return res;
    })
    .catch(() => null);
  if (cached) {
    event.waitUntil(refresh);
    return cached;
  }
  return (await refresh) || Response.error();
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Cross-origin (Supabase product images, Google Fonts): leave to the browser. This also keeps them
  // outside the worker's own CSP, which only allows same-origin fetches.
  if (url.origin !== self.location.origin) return;
  // Video/audio use Range requests (206), which the Cache API cannot store.
  if (req.headers.has('range')) return;
  if (url.pathname === '/sw.js') return;

  if (req.mode === 'navigate') {
    event.respondWith(navigate(event));
    return;
  }
  if (url.pathname.startsWith('/static/') && !url.pathname.startsWith('/static/videos/')) {
    event.respondWith(staleWhileRevalidate(event));
  }
});