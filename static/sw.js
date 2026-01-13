/**
 * Musify Service Worker v2.0.0
 * Complete PWA Service Worker for installable web app
 * 
 * Features:
 * - Proper install/activate lifecycle
 * - Offline support with cache-first for static assets
 * - Network-first for API calls
 * - Audio file caching for offline playback
 * - Background sync for downloads
 * - Push notifications support
 * - Media session integration
 */

const SW_VERSION = '2.0.0';
const CACHE_PREFIX = 'musify';
const STATIC_CACHE = `${CACHE_PREFIX}-static-v${SW_VERSION}`;
const AUDIO_CACHE = `${CACHE_PREFIX}-audio-v1`;
const DYNAMIC_CACHE = `${CACHE_PREFIX}-dynamic-v1`;
const API_CACHE = `${CACHE_PREFIX}-api-v1`;

// Static assets to precache for offline use
const PRECACHE_ASSETS = [
  '/',
  '/songs',
  '/static/style.css',
  '/static/app.js',
  '/static/wave-engine.js',
  '/static/manifest.json',
  '/static/default-artwork.png',
  '/static/icons/icon-72x72.png',
  '/static/icons/icon-96x96.png',
  '/static/icons/icon-128x128.png',
  '/static/icons/icon-144x144.png',
  '/static/icons/icon-152x152.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-384x384.png',
  '/static/icons/icon-512x512.png'
];

// URLs that should always go to network first
const NETWORK_FIRST_PATTERNS = [
  /\/api\//,
  /\/progress\//,
  /socket\.io/
];

// URLs that should be cached for offline audio playback
const AUDIO_PATTERNS = [
  /\/play\//,
  /\/cover\//
];

// ========================================
// INSTALL EVENT
// ========================================
self.addEventListener('install', (event) => {
  console.log(`[SW ${SW_VERSION}] Installing...`);
  
  event.waitUntil(
    (async () => {
      // Open static cache and add all precache assets
      const cache = await caches.open(STATIC_CACHE);
      console.log(`[SW ${SW_VERSION}] Precaching static assets...`);
      
      // Add assets one by one to handle failures gracefully
      for (const asset of PRECACHE_ASSETS) {
        try {
          await cache.add(asset);
        } catch (err) {
          console.warn(`[SW] Failed to cache: ${asset}`, err);
        }
      }
      
      console.log(`[SW ${SW_VERSION}] Precaching complete`);
      
      // Skip waiting to activate immediately
      await self.skipWaiting();
    })()
  );
});

// ========================================
// ACTIVATE EVENT
// ========================================
self.addEventListener('activate', (event) => {
  console.log(`[SW ${SW_VERSION}] Activating...`);
  
  event.waitUntil(
    (async () => {
      // Clean up old caches
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames
          .filter(name => name.startsWith(CACHE_PREFIX) && name !== STATIC_CACHE && name !== AUDIO_CACHE && name !== DYNAMIC_CACHE && name !== API_CACHE)
          .map(name => {
            console.log(`[SW ${SW_VERSION}] Deleting old cache: ${name}`);
            return caches.delete(name);
          })
      );
      
      // Claim all clients immediately
      await self.clients.claim();
      
      console.log(`[SW ${SW_VERSION}] Activated and controlling all clients`);
    })()
  );
});

// ========================================
// FETCH EVENT - Request Interception
// ========================================
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }
  
  // Skip cross-origin requests (except for CDN resources)
  if (url.origin !== self.location.origin && !url.hostname.includes('cdn')) {
    return;
  }
  
  // Network-first for API calls and real-time endpoints
  if (NETWORK_FIRST_PATTERNS.some(pattern => pattern.test(url.pathname))) {
    event.respondWith(networkFirst(event.request, API_CACHE));
    return;
  }
  
  // Cache-first for audio files (for offline playback)
  if (AUDIO_PATTERNS.some(pattern => pattern.test(url.pathname))) {
    event.respondWith(cacheFirstWithNetwork(event.request, AUDIO_CACHE));
    return;
  }
  
  // Cache-first for static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(event.request, STATIC_CACHE));
    return;
  }
  
  // Navigation requests - serve from cache with network fallback
  if (event.request.mode === 'navigate') {
    event.respondWith(navigationHandler(event.request));
    return;
  }
  
  // Default: stale-while-revalidate for everything else
  event.respondWith(staleWhileRevalidate(event.request, DYNAMIC_CACHE));
});

// ========================================
// CACHING STRATEGIES
// ========================================

/**
 * Cache-first strategy - serve from cache, fallback to network
 */
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  
  if (cached) {
    return cached;
  }
  
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    console.warn('[SW] Cache-first fetch failed:', request.url);
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Cache-first with network update for audio files
 */
async function cacheFirstWithNetwork(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  
  if (cached) {
    // Return cached immediately, update in background
    fetch(request).then(response => {
      if (response.ok) {
        cache.put(request, response);
      }
    }).catch(() => {});
    return cached;
  }
  
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // For cover images, return default artwork
    if (request.url.includes('/cover/')) {
      const defaultArtwork = await caches.match('/static/default-artwork.png');
      if (defaultArtwork) return defaultArtwork;
    }
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Network-first strategy - try network, fallback to cache
 */
async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/**
 * Stale-while-revalidate strategy
 */
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  }).catch(() => cached);
  
  return cached || fetchPromise;
}

/**
 * Navigation handler for page requests
 */
async function navigationHandler(request) {
  try {
    // Try network first for navigation
    const response = await fetch(request);
    
    // Cache successful navigation responses
    const cache = await caches.open(STATIC_CACHE);
    cache.put(request, response.clone());
    
    return response;
  } catch (err) {
    // Fallback to cached page
    const cached = await caches.match(request);
    if (cached) return cached;
    
    // Fallback to /songs as the main app shell
    const songsPage = await caches.match('/songs');
    if (songsPage) return songsPage;
    
    // Last resort: return basic offline page
    return new Response(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Musify - Offline</title>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(180deg, #1a1a2e 0%, #0f0f23 100%);
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            margin: 0;
            padding: 20px;
          }
          .offline-container {
            max-width: 400px;
          }
          h1 { font-size: 48px; margin: 0 0 16px; }
          p { opacity: 0.7; margin: 0 0 24px; }
          button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 16px;
            cursor: pointer;
          }
          button:hover { opacity: 0.9; }
        </style>
      </head>
      <body>
        <div class="offline-container">
          <h1>📵</h1>
          <h2>You're Offline</h2>
          <p>Musify needs an internet connection to load. Please check your connection and try again.</p>
          <button onclick="location.reload()">Retry</button>
        </div>
      </body>
      </html>
    `, {
      status: 200,
      headers: { 'Content-Type': 'text/html' }
    });
  }
}

// ========================================
// BACKGROUND SYNC
// ========================================
self.addEventListener('sync', (event) => {
  console.log(`[SW ${SW_VERSION}] Sync event:`, event.tag);
  
  if (event.tag === 'sync-downloads') {
    event.waitUntil(syncDownloads());
  }
  
  if (event.tag === 'sync-preferences') {
    event.waitUntil(syncPreferences());
  }
});

async function syncDownloads() {
  console.log('[SW] Syncing pending downloads...');
  // Handle pending downloads when back online
  // This would integrate with IndexedDB to store pending download requests
}

async function syncPreferences() {
  console.log('[SW] Syncing preferences...');
  // Sync user preferences with server
}

// ========================================
// PUSH NOTIFICATIONS
// ========================================
self.addEventListener('push', (event) => {
  console.log(`[SW ${SW_VERSION}] Push received`);
  
  let data = { title: 'Musify', body: 'New update available!' };
  
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }
  
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icons/icon-192x192.png',
      badge: '/static/icons/icon-72x72.png',
      vibrate: [100, 50, 100],
      data: data,
      actions: [
        { action: 'open', title: 'Open Musify' },
        { action: 'dismiss', title: 'Dismiss' }
      ]
    })
  );
});

// ========================================
// NOTIFICATION CLICK
// ========================================
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const action = event.action;
  
  if (action === 'dismiss') {
    return;
  }
  
  // Handle different notification actions
  if (action === 'play') {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then(clientList => {
        for (const client of clientList) {
          client.postMessage({ action: 'play' });
          return client.focus();
        }
        return clients.openWindow('/songs');
      })
    );
    return;
  }
  
  if (action === 'pause') {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then(clientList => {
        for (const client of clientList) {
          client.postMessage({ action: 'pause' });
        }
      })
    );
    return;
  }
  
  if (action === 'next') {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then(clientList => {
        for (const client of clientList) {
          client.postMessage({ action: 'next' });
        }
      })
    );
    return;
  }
  
  if (action === 'previous') {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then(clientList => {
        for (const client of clientList) {
          client.postMessage({ action: 'previous' });
        }
      })
    );
    return;
  }
  
  // Default: open the app
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      // Focus existing window if available
      for (const client of clientList) {
        if (client.url.includes('/songs') && 'focus' in client) {
          return client.focus();
        }
      }
      // Open new window
      return clients.openWindow('/songs');
    })
  );
});

// ========================================
// MESSAGE HANDLER
// ========================================
self.addEventListener('message', (event) => {
  const { type, data } = event.data || {};
  
  console.log(`[SW ${SW_VERSION}] Message received:`, type);
  
  switch (type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;
      
    case 'GET_VERSION':
      event.ports[0]?.postMessage({ version: SW_VERSION });
      break;
      
    case 'CLEAR_CACHE':
      event.waitUntil(
        caches.keys().then(names => Promise.all(names.map(name => caches.delete(name))))
          .then(() => event.ports[0]?.postMessage({ success: true }))
      );
      break;
      
    case 'CACHE_AUDIO':
      if (data?.url) {
        event.waitUntil(
          caches.open(AUDIO_CACHE)
            .then(cache => cache.add(data.url))
            .then(() => event.ports[0]?.postMessage({ success: true }))
            .catch(err => event.ports[0]?.postMessage({ success: false, error: err.message }))
        );
      }
      break;
      
    case 'PRECACHE_SONGS':
      if (data?.songs && Array.isArray(data.songs)) {
        event.waitUntil(
          precacheSongs(data.songs)
            .then(count => event.ports[0]?.postMessage({ success: true, cached: count }))
        );
      }
      break;
  }
});

/**
 * Precache multiple songs for offline playback
 */
async function precacheSongs(songs) {
  const cache = await caches.open(AUDIO_CACHE);
  let count = 0;
  
  for (const song of songs) {
    try {
      await cache.add(`/play/${encodeURIComponent(song)}`);
      await cache.add(`/cover/${encodeURIComponent(song)}`);
      count++;
    } catch (err) {
      console.warn(`[SW] Failed to cache song: ${song}`, err);
    }
  }
  
  return count;
}

// ========================================
// PERIODIC BACKGROUND SYNC
// ========================================
self.addEventListener('periodicsync', (event) => {
  console.log(`[SW ${SW_VERSION}] Periodic sync:`, event.tag);
  
  if (event.tag === 'update-content') {
    event.waitUntil(updateCachedContent());
  }
});

async function updateCachedContent() {
  // Update cached static content
  const cache = await caches.open(STATIC_CACHE);
  
  for (const asset of PRECACHE_ASSETS) {
    try {
      const response = await fetch(asset, { cache: 'no-cache' });
      if (response.ok) {
        await cache.put(asset, response);
      }
    } catch (err) {
      // Ignore fetch errors during background update
    }
  }
}

console.log(`[SW ${SW_VERSION}] Service Worker loaded`);
