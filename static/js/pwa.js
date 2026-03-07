// static/js/pwa.js
// ============================================================================
// PWA: регистрация Service Worker, промпт установки, уведомления об обновлении,
// обработка shortcuts (?action=...) и deep links (web+vortex://).
// Подключается в main.js: import './pwa.js';
// ============================================================================

let _deferredInstallPrompt = null;   // браузер сохранил событие beforeinstallprompt
let _swRegistration        = null;   // текущая регистрация SW

// ─── Инициализация ────────────────────────────────────────────────────────────
export async function initPWA() {
    if (!('serviceWorker' in navigator)) {
        console.log('[PWA] Service Worker не поддерживается');
        return;
    }

    await _registerServiceWorker();
    _handleInstallPrompt();
    _handleShortcuts();
    _handleProtocolHandler();
    _listenForSWMessages();
}

// ─── Регистрация Service Worker ───────────────────────────────────────────────
async function _registerServiceWorker() {
    try {
        _swRegistration = await navigator.serviceWorker.register('/service-worker.js', {
            scope: '/',
            updateViaCache: 'none',   // всегда проверяем обновления SW
        });

        console.log('[PWA] SW зарегистрирован, scope:', _swRegistration.scope);

        // Следим за обновлением SW
        _swRegistration.addEventListener('updatefound', () => {
            const newWorker = _swRegistration.installing;
            if (!newWorker) return;

            newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                    // Новый SW установлен, показываем баннер обновления
                    _showUpdateBanner(newWorker);
                }
            });
        });

        // Проверяем обновления при каждом открытии страницы
        _swRegistration.update();

    } catch (err) {
        console.error('[PWA] Ошибка регистрации SW:', err);
    }
}

// ─── Баннер «Доступно обновление» ────────────────────────────────────────────
function _showUpdateBanner(newWorker) {
    const existing = document.getElementById('pwa-update-banner');
    if (existing) return;

    const banner = document.createElement('div');
    banner.id = 'pwa-update-banner';
    banner.style.cssText = [
        'position:fixed', 'bottom:20px', 'left:50%', 'transform:translateX(-50%)',
        'background:#1a1a2e', 'border:1px solid #4ecdc4', 'border-radius:12px',
        'padding:14px 20px', 'z-index:99999',
        'display:flex', 'align-items:center', 'gap:14px',
        'box-shadow:0 8px 32px rgba(0,0,0,.6)',
        'font-family:system-ui,sans-serif', 'font-size:14px', 'color:#e0e0e0',
        'max-width:360px',
    ].join(';');
    banner.innerHTML = `
        <span style="font-size:20px">🔄</span>
        <span style="flex:1">Доступна новая версия VORTEX</span>
        <button id="pwa-update-btn"
            style="background:#4ecdc4;color:#0a0a12;border:none;border-radius:8px;
                   padding:6px 14px;font-weight:700;cursor:pointer;font-size:13px;
                   white-space:nowrap">
            Обновить
        </button>
        <button id="pwa-update-close"
            style="background:none;border:none;color:#555;cursor:pointer;font-size:18px;
                   line-height:1;padding:0">×</button>
    `;
    document.body.appendChild(banner);

    document.getElementById('pwa-update-btn').onclick = () => {
        newWorker.postMessage({ type: 'skip-waiting' });
        window.location.reload();
    };
    document.getElementById('pwa-update-close').onclick = () => banner.remove();

    // Авто-скрыть через 15 сек
    setTimeout(() => banner?.remove(), 15000);
}

// ─── Промпт «Установить приложение» ──────────────────────────────────────────
function _handleInstallPrompt() {
    window.addEventListener('beforeinstallprompt', e => {
        e.preventDefault();
        _deferredInstallPrompt = e;
        _showInstallButton();
        console.log('[PWA] beforeinstallprompt перехвачен');
    });

    window.addEventListener('appinstalled', () => {
        console.log('[PWA] Приложение установлено');
        _deferredInstallPrompt = null;
        document.getElementById('pwa-install-btn')?.remove();
        _showToast('✅ VORTEX установлен как приложение');
    });
}

function _showInstallButton() {
    if (document.getElementById('pwa-install-btn')) return;

    // Встраиваем кнопку в sidebar footer или создаём floating
    const footer = document.querySelector('.sidebar-footer');
    const btn = document.createElement('button');
    btn.id = 'pwa-install-btn';
    btn.className = 'footer-btn';
    btn.title = 'Установить как приложение';
    btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
             fill="currentColor" viewBox="0 0 24 24">
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
        </svg>
        <div>Установить</div>
    `;
    btn.onclick = _triggerInstall;

    if (footer) footer.insertBefore(btn, footer.firstChild);
    else {
        // Floating кнопка если sidebar недоступен
        btn.style.cssText = [
            'position:fixed', 'bottom:20px', 'right:20px', 'z-index:1000',
            'background:#4ecdc4', 'color:#0a0a12', 'border:none',
            'border-radius:50px', 'padding:10px 18px',
            'display:flex', 'align-items:center', 'gap:8px',
            'font-weight:700', 'cursor:pointer', 'font-size:13px',
            'box-shadow:0 4px 16px rgba(78,205,196,.4)',
        ].join(';');
        document.body.appendChild(btn);
    }
}

export async function _triggerInstall() {
    if (!_deferredInstallPrompt) return;
    _deferredInstallPrompt.prompt();
    const { outcome } = await _deferredInstallPrompt.userChoice;
    console.log('[PWA] Результат установки:', outcome);
    _deferredInstallPrompt = null;
    document.getElementById('pwa-install-btn')?.remove();
}

// ─── Обработка shortcuts (?action=...) ───────────────────────────────────────
function _handleShortcuts() {
    const params = new URLSearchParams(location.search);
    const action = params.get('action');
    if (!action) return;

    // Убираем параметр из URL без перезагрузки
    const cleanUrl = location.pathname;
    history.replaceState({}, '', cleanUrl);

    // Выполняем действие после инициализации приложения
    window.addEventListener('vortex:ready', () => {
        if (action === 'create-room') {
            setTimeout(() => window.showCreateRoomModal?.(), 300);
        }
        if (action === 'join-room') {
            setTimeout(() => window.showJoinModal?.(), 300);
        }
    }, { once: true });
}

// ─── Обработка protocol handler (web+vortex://...) ───────────────────────────
function _handleProtocolHandler() {
    const params = new URLSearchParams(location.search);
    const invite = params.get('invite');
    if (!invite) return;

    history.replaceState({}, '', location.pathname);

    window.addEventListener('vortex:ready', () => {
        setTimeout(() => {
            if (window.showJoinModal) {
                window.showJoinModal();
                const input = document.getElementById('join-code');
                if (input) {
                    input.value = invite.replace('web+vortex://', '').toUpperCase();
                }
            }
        }, 400);
    }, { once: true });
}

// ─── Слушаем сообщения от SW ──────────────────────────────────────────────────
function _listenForSWMessages() {
    navigator.serviceWorker.addEventListener('message', event => {
        const { type, url } = event.data || {};

        if (type === 'network-restored') {
            console.log('[PWA] Сеть восстановлена, переподключаемся...');
            // Инициируем переподключение WebSocket если он был разорван
            window.AppState?.currentRoom?.id &&
            window.connectWS?.(window.AppState.currentRoom.id);
        }

        if (type === 'notification-click' && url) {
            console.log('[PWA] Клик по уведомлению, переход к:', url);
        }

        if (type === 'cache-cleared') {
            _showToast('🗑 Кэш очищен');
        }
    });
}

// ─── Push-уведомления ─────────────────────────────────────────────────────────
/**
 * Запрашивает разрешение на push-уведомления и подписывается.
 * Вызывать при первом входе пользователя в комнату.
 */
export async function requestNotificationPermission() {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission === 'denied') return false;

    const permission = await Notification.requestPermission();
    console.log('[PWA] Разрешение на уведомления:', permission);
    return permission === 'granted';
}

/**
 * Показывает нативное уведомление о новом сообщении.
 * Вызывается из chat.js когда вкладка не в фокусе.
 */
export function showMessageNotification(senderName, messageText, roomName, roomId) {
    if (Notification.permission !== 'granted') return;
    if (document.visibilityState === 'visible') return;  // вкладка в фокусе — не нужно

    const notification = new Notification(`${senderName} → ${roomName}`, {
        body:    messageText.length > 80 ? messageText.slice(0, 80) + '...' : messageText,
        icon:    '/static/icons/icon-192.png',
        badge:   '/static/icons/icon-72.png',
        tag:     `vortex-room-${roomId}`,
        renotify: true,
        silent:  false,
    });

    notification.onclick = () => {
        window.focus();
        notification.close();
    };

    // Авто-закрыть через 5 сек
    setTimeout(() => notification.close(), 5000);
}

// ─── Утилита: тост-уведомление ────────────────────────────────────────────────
function _showToast(message, duration = 3000) {
    const toast = document.createElement('div');
    toast.style.cssText = [
        'position:fixed', 'bottom:20px', 'left:50%', 'transform:translateX(-50%)',
        'background:#1a1a2e', 'border:1px solid rgba(255,255,255,.1)',
        'border-radius:8px', 'padding:10px 18px',
        'font-size:13px', 'color:#e0e0e0', 'z-index:99999',
        'pointer-events:none', 'white-space:nowrap',
        'box-shadow:0 4px 16px rgba(0,0,0,.4)',
    ].join(';');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

// ─── Проверка: запущен ли как PWA ────────────────────────────────────────────
export function isRunningAsPWA() {
    return (
        window.matchMedia('(display-mode: standalone)').matches ||
        window.matchMedia('(display-mode: fullscreen)').matches  ||
        window.navigator.standalone === true                     // iOS Safari
    );
}

// ─── Очистка кэша (для debug / сброса) ───────────────────────────────────────
export function clearSWCache() {
    navigator.serviceWorker.controller?.postMessage({ type: 'clear-cache' });
}