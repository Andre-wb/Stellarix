// static/js/main.js
// ============================================================================
// Главный модуль приложения. Инициализирует глобальное состояние, загружает
// все модули и запускает приложение после успешной аутентификации.
// ============================================================================

import { $, loadCsrfToken, api, openModal, closeModal } from './utils.js';
import { checkSession }    from './auth.js';
import { initPWA, showMessageNotification, requestNotificationPermission } from './pwa.js';
import { startPeerPolling } from './peers.js';
import { showWelcome }     from './ui.js';

import * as auth        from './auth.js';
import * as rooms       from './rooms.js';
import * as peers       from './peers.js';
import * as webrtc      from './webrtc.js';
import * as ui          from './ui.js';
import * as chat        from './chat/chat.js';
import * as fileUpload  from './chat/file-upload.js';
import * as imageViewer from './chat/image-viewer.js';
import {_msgTexts } from './chat/messages.js';
window._msgTexts = _msgTexts;


// Глобальное состояние приложения
window.AppState = {
    user:          null,          // данные текущего пользователя
    rooms:         [],            // список комнат
    currentRoom:   null,          // текущая комната
    token:         null,          // не используется напрямую (хранится в куках)
    ws:            null,          // WebSocket чата
    signalWs:      null,          // WebSocket для сигнализации WebRTC
    peers:         [],            // устройства в локальной сети
    peersInterval: null,          // интервал опроса пиров
    typingTimeout: null,          // таймаут для снятия статуса печати
    selectedEmoji: '👤',          // выбранный эмодзи при регистрации
    pc:            null,          // RTCPeerConnection
    localStream:   null,          // локальный медиапоток
    isMuted:       false,         // состояние микрофона
    isCamOff:      false,         // состояние камеры
    nodePublicKey: null,          // публичный ключ X25519 ноды
    sessionKeys:   {},            // сессионные ключи для пиров (не используется в этих файлах)
    csrfToken:     null,          // токен для защиты от CSRF
    x25519PrivateKey: null
};

// Экспортируем функции всех модулей в глобальную область видимости,
// чтобы они были доступны из HTML-обработчиков (onclick и т.д.)
Object.assign(window, auth, rooms, chat, peers, webrtc, ui, fileUpload, imageViewer);
window.openModal  = openModal;
window.closeModal = closeModal;
window.showMessageNotification = showMessageNotification;
window.requestNotificationPermission = requestNotificationPermission;

/**
 * Запускает приложение после успешной аутентификации.
 * Скрывает экран входа, заполняет данные сайдбара, загружает CSRF-токен,
 * получает публичный ключ ноды, загружает комнаты, запускает поиск пиров,
 * инициализирует просмотрщик изображений и динамически подгружает опциональные модули.
 */
window.bootApp = async function bootApp() {
    $('auth-screen').style.display = 'none';
    $('app').style.display         = 'flex';

    // Заполняем информацию о пользователе в сайдбаре
    $('sb-avatar').textContent = AppState.user.avatar_emoji || '👤';
    $('sb-name').textContent   = AppState.user.display_name || AppState.user.username;
    $('sb-phone').textContent  = AppState.user.phone;

    // PWA: регистрация SW, промпт установки, shortcuts
    initPWA();

    // Загружаем CSRF-токен и обновляем его каждые 10 минут
    await loadCsrfToken();
    setInterval(loadCsrfToken, 600_000);

    // Получаем публичный ключ ноды для E2E (опционально)
    try {
        const d = await api('GET', '/api/keys/pubkey');
        AppState.nodePublicKey = d.pubkey_hex;
        console.log('🔑 X25519 pubkey:', AppState.nodePublicKey.slice(0, 16) + '...');
    } catch {}

    // Загружаем список комнат и начинаем опрос пиров
    await rooms.loadMyRooms();
    startPeerPolling();

    // Инициализируем просмотрщик изображений
    if (typeof imageViewer.initImageViewer === 'function') {
        imageViewer.initImageViewer();
    }

    // Динамически подгружаем необязательные модули (чтобы не ломать приложение при их отсутствии)
    try {
        const voiceRecorder = await import('./voice_recorder.js');
        Object.assign(window, voiceRecorder);
        if (typeof voiceRecorder.initVoiceRecorder === 'function') {
            voiceRecorder.initVoiceRecorder();
        }
        console.log('🎙 voice_recorder загружен');
    } catch (e) {
        console.warn('voice_recorder.js не загружен:', e.message);
    }

    try {
        const photoEditor = await import('./photo_editor.js');
        Object.assign(window, photoEditor);
        console.log('📷 photo_editor загружен');
    } catch (e) {
        console.warn('photo_editor.js не загружен:', e.message);
    }

    // Показываем приветственный экран (выбор комнаты)
    showWelcome();
};

// Закрытие модальных окон при клике на затемнённый фон
document.querySelectorAll('.modal-overlay').forEach(el => {
    el.addEventListener('click', e => {
        if (e.target === el) el.classList.remove('show');
    });
});

// Обработчик нажатия Enter на форме входа
document.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const loginForm = document.getElementById('login-form');
    if (!loginForm || loginForm.style.display === 'none') return;
    const focused = document.activeElement;
    if (focused === document.getElementById('l-login') ||
        focused === document.getElementById('l-pass')) {
        window.doLogin?.();
    }
});

// При загрузке страницы проверяем, есть ли активная сессия
window.addEventListener('DOMContentLoaded', checkSession);

window.addEventListener('DOMContentLoaded', async () => {
    await loadCsrfToken();
    checkSession();
});