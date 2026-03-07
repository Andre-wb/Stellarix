// ============================================================================
// VORTEX Service Worker
// Стратегии кэширования:
//   — Статика (JS/CSS/иконки)  → Cache-First (быстрый старт офлайн)
//   — API запросы              → Network-First (актуальные данные)
//   — HTML страница            → Network-First + офлайн-заглушка
// ============================================================================

const CACHE_NAME     = 'vortex-v1';
const STATIC_CACHE   = 'vortex-static-v1';
const API_CACHE      = 'vortex-api-v1';

// Ресурсы для предварительного кэширования при установке SW
const PRECACHE_URLS = [
    '/',
    '/static/css/main.css',
    '/static/css/menu.css',
    '/static/js/main.js',
    '/static/js/auth.js',
    '/static/js/crypto.js',
    '/static/js/rooms.js',
    '/static/js/peers.js',
    '/static/js/webrtc.js',
    '/static/js/ui.js',
    '/static/js/utils.js',
    '/static/js/photo_editor.js',
    '/static/js/voice_recorder.js',
    '/static/js/chat/chat.js',
    '/static/js/chat/messages.js',
    '/static/js/chat/file-upload.js',
    '/static/js/chat/image-viewer.js',
    '/static/js/chat/liquid-glass.js',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
];

// HTML заглушка для офлайн-режима (когда нет ни кэша, ни сети)
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VORTEX — офлайн</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0a0a12;
      color: #e0e0e0;
      font-family: system-ui, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      text-align: center;
      padding: 24px;
    }
    .logo {
      font-size: 32px;
      font-weight: 900;
      letter-spacing: 8px;
      color: #4ecdc4;
      margin-bottom: 8px;
    }
    .sub {
      font-size: 13px;
      color: #555;
      margin-bottom: 40px;
      letter-spacing: 2px;
      text-transform: uppercase;
    }
    .card {
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 16px;
      padding: 32px 40px;
      max-width: 380px;
    }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h2 { font-size: 18px; margin-bottom: 8px; color: #fff; }
    p { font-size: 14px; color: #888; line-height: 1.6; margin-bottom: 24px; }
    .hint {
      font-size: 12px;
      color: #444;
      background: rgba(255,255,255,.02);
      border-radius: 8px;
      padding: 12px;
      font-family: monospace;
    }
    button {
      margin-top: 20px;
      padding: 10px 24px;
      background: #4ecdc4;
      color: #0a0a12;
      border: none;
      border-radius: 8px;
      font-weight: 700;
      cursor: pointer;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="logo">VORTEX</div>
  <div class="sub">децентрализованный чат</div>
  <div class="card">
    <div class="icon">📡</div>
    <h2>Нет соединения с узлом</h2>
    <p>Убедись, что VORTEX запущен на этом устройстве или в той же локальной сети.</p>
    <div class="hint">python run.py</div>
    <button onclick="location.reload()">Повторить подключение</button>
  </div>
</body>
</html>`;

// ─── Установка SW ─────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
    console.log('[SW] Установка, кэширование статики...');
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())   // активируемся сразу, не ждём закрытия вкладок
            .catch(err => console.warn('[SW] Ошибка прекэширования:', err))
    );
});

// ─── Активация: удаляем устаревшие кэши ──────────────────────────────────────
self.addEventListener('activate', event => {
    console.log('[SW] Активация, чистка старых кэшей...');
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(k => k !== STATIC_CACHE && k !== API_CACHE)
                    .map(k => { console.log('[SW] Удаляю кэш:', k); return caches.delete(k); })
            )
        ).then(() => self.clients.claim())  // берём под управление все открытые вкладки
    );
});

// ─── Перехват запросов ────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // WebSocket — не трогаем (SW не может перехватывать WS)
    if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

    // API запросы → Network-First (свежие данные важнее)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(networkFirst(request, API_CACHE, 5000));
        return;
    }

    // Статика (JS/CSS/иконки/изображения) → Cache-First (быстро и офлайн)
    if (
        url.pathname.startsWith('/static/') ||
        url.pathname.match(/\.(js|css|png|svg|ico|woff2?)$/)
    ) {
        event.respondWith(cacheFirst(request, STATIC_CACHE));
        return;
    }

    // HTML страница → Network-First + офлайн-заглушка
    if (request.headers.get('accept')?.includes('text/html')) {
        event.respondWith(networkFirstWithOfflineFallback(request));
        return;
    }

    // Всё остальное — обычный fetch
    event.respondWith(fetch(request));
});

// ─── Стратегия Cache-First ────────────────────────────────────────────────────
async function cacheFirst(request, cacheName) {
    const cached = await caches.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        return new Response('Ресурс недоступен офлайн', { status: 503 });
    }
}

// ─── Стратегия Network-First ──────────────────────────────────────────────────
async function networkFirst(request, cacheName, timeoutMs = 5000) {
    // Гонка: сеть vs таймаут
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(request, { signal: controller.signal });
        clearTimeout(timer);

        if (response.ok && request.method === 'GET') {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        clearTimeout(timer);
        // Сеть недоступна — берём из кэша
        const cached = await caches.match(request);
        if (cached) return cached;
        return new Response(
            JSON.stringify({ error: 'Сеть недоступна, узел VORTEX не отвечает' }),
            { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
    }
}

// ─── Network-First с HTML-заглушкой ──────────────────────────────────────────
async function networkFirstWithOfflineFallback(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        const cached = await caches.match(request);
        if (cached) return cached;
        return new Response(OFFLINE_HTML, {
            headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
    }
}

// ─── Push-уведомления ─────────────────────────────────────────────────────────
self.addEventListener('push', event => {
    if (!event.data) return;

    let data;
    try { data = event.data.json(); }
    catch { data = { title: 'VORTEX', body: event.data.text() }; }

    const options = {
        body:    data.body    || 'Новое сообщение',
        icon:    data.icon    || '/static/icons/icon-192.png',
        badge:   data.badge   || '/static/icons/icon-72.png',
        tag:     data.tag     || 'vortex-message',
        renotify: !!data.renotify,
        silent:  false,
        vibrate: [100, 50, 100],
        data:    { url: data.url || '/', roomId: data.roomId },
        actions: [
            { action: 'open',    title: 'Открыть', icon: '/static/icons/icon-72.png' },
            { action: 'dismiss', title: 'Закрыть' },
        ],
    };

    event.waitUntil(
        self.registration.showNotification(data.title || 'VORTEX', options)
    );
});

// ─── Клик по уведомлению ──────────────────────────────────────────────────────
self.addEventListener('notificationclick', event => {
    event.notification.close();

    if (event.action === 'dismiss') return;

    const targetUrl = event.notification.data?.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(windowClients => {
                // Есть открытая вкладка VORTEX — фокусируемся на ней
                for (const client of windowClients) {
                    if (new URL(client.url).origin === self.location.origin) {
                        client.focus();
                        client.postMessage({ type: 'notification-click', url: targetUrl });
                        return;
                    }
                }
                // Нет открытой вкладки — открываем новую
                return clients.openWindow(targetUrl);
            })
    );
});

// ─── Background Sync (отложенная отправка при восстановлении сети) ────────────
self.addEventListener('sync', event => {
    if (event.tag === 'vortex-send-messages') {
        event.waitUntil(flushPendingMessages());
    }
});

async function flushPendingMessages() {
    // Уведомляем все вкладки что сеть восстановлена — они сами переподключатся
    const allClients = await clients.matchAll({ type: 'window' });
    allClients.forEach(client =>
        client.postMessage({ type: 'network-restored' })
    );
}

// ─── Получение сообщений от страницы ─────────────────────────────────────────
self.addEventListener('message', event => {
    if (event.data?.type === 'skip-waiting') {
        self.skipWaiting();
    }
    // Принудительная чистка кэша по команде со страницы
    if (event.data?.type === 'clear-cache') {
        caches.keys().then(keys =>
            Promise.all(keys.map(k => caches.delete(k)))
        ).then(() => {
            event.source?.postMessage({ type: 'cache-cleared' });
        });
    }
});