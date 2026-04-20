// static/js/main.js
// ============================================================================
// Главный модуль приложения. Инициализирует глобальное состояние, загружает
// все модули и запускает приложение после успешной аутентификации.
// ============================================================================

import { $, loadCsrfToken, api, openModal, closeModal } from './utils.js';
import { checkSession }    from './auth.js';
import { initPWA, showMessageNotification, requestNotificationPermission, subscribePush } from './pwa.js';
import { startPeerPolling } from './peers.js';
import { showWelcome, openRoom, updateSidebarStatus, openStatusEditor } from './ui.js';
import { startOnboarding, isOnboardingDone } from './onboarding.js';
import { initLangPicker } from './lang-picker.js';
import * as userProfile from './user-profile.js';

import * as auth        from './auth.js';
import * as rooms       from './rooms.js';
import * as peers       from './peers.js';
import * as webrtc      from './webrtc.js';
import * as ui          from './ui.js';
import * as chat        from './chat/chat.js';
import * as fileUpload  from './chat/file-upload.js';
import './chat/page-builder.js';
import './chat/article.js';
import './chat/chat-ux.js';
import './sticker-manager.js';
import { startBMP, registerBMPHandler, registerRoomSecret, MSG } from './bmp-client.js';
import * as imageViewer from './chat/image-viewer.js';
import * as contacts     from './contacts.js';
import * as saved        from './saved.js';
import * as tasks        from './tasks.js';
import * as notifications from './notifications.js';
import * as notifSounds  from './notification-sounds.js';
import * as voiceChannel from './voice_channel.js';
import * as spaces       from './spaces.js';
import * as fingerprint  from './fingerprint.js';
import * as groupCall   from './group_call.js';
import * as mediaViewer from './chat/media-viewer.js';
import * as contactSync from './contact_sync.js';
import * as stream      from './stream.js';
import * as keyBackup   from './key_backup.js';
import * as emojiPicker  from './chat/emoji-picker.js';
import * as skeletons    from './chat/skeletons.js';
import { invalidateStickerCache } from './chat/emoji-picker.js';
import * as shortcuts    from './shortcuts.js';
import * as a11y         from './a11y.js';
import * as gestures     from './gestures.js';
import * as toast        from './toast.js';
import * as netStatus    from './network_status.js';
import * as preferences  from './preferences.js';
import * as phonePassword from './phone_password.js';
import * as federation   from './settings/federation.js';
import * as zkCrypto     from './zk-crypto.js';
import { t, setLocale, getLocale, initI18n, getSupportedLocales } from './i18n.js';
import {_msgTexts } from './chat/messages.js';
import './chat/ai-text.js';
window._msgTexts = _msgTexts;
window._toggleEmojiPicker    = emojiPicker.togglePicker;
window._invalidateStickerCache = invalidateStickerCache;
window._sendStickerFromPicker  = (text) => chat.sendStickerDirect(text);
window._showUploadProgress = skeletons.showUploadProgress;
window._updateUploadProgress = skeletons.updateUploadProgress;
window._removeUploadProgress = skeletons.removeUploadProgress;
window._openModalA11y = a11y.openModalA11y;
window._closeModalA11y = a11y.closeModalA11y;
window._announce = a11y.announce;
window.t = t;
window._i18n_t = t;  // separate ref for inline-handlers.js (avoids recursion with its own var t)
window.setLocale = setLocale;
window.getLocale = getLocale;


// Глобальное состояние приложения
window.AppState = {
    user:          null,          // данные текущего пользователя
    rooms:         [],            // список комнат
    currentRoom:   null,          // текущая комната
    contacts:      [],            // список контактов
    dms:           [],            // личные сообщения
    notifWs:       null,          // WebSocket уведомлений
    token:         null,          // не используется напрямую (хранится в куках)
    ws:            null,          // WebSocket чата
    signalWs:      null,          // WebSocket для сигнализации WebRTC
    spaces:        [],            // спейсы пользователя
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
    x25519PrivateKey: null,
    networkMode:      'local',
};

// Экспортируем функции всех модулей в глобальную область видимости,
// чтобы они были доступны из HTML-обработчиков (onclick и т.д.)
Object.assign(window, auth, rooms, chat, peers, webrtc, ui, fileUpload, imageViewer, contacts, saved, tasks, notifications, notifSounds, voiceChannel, spaces, userProfile, fingerprint, groupCall, contactSync, stream, keyBackup, gestures, toast, netStatus, preferences, phonePassword, federation, zkCrypto);
window.openModal  = openModal;
window.closeModal = closeModal;
window.openStatusEditor = openStatusEditor;
window.api        = api;
window.showMessageNotification = showMessageNotification;
window.requestNotificationPermission = requestNotificationPermission;

// DND toggle handler for the settings UI checkbox
window._toggleDND = function(enabled) {
    notifSounds.setDND(enabled);
};


/**
 * Запускает приложение после успешной аутентификации.
 * Скрывает экран входа, заполняет данные сайдбара, загружает CSRF-токен,
 * получает публичный ключ ноды, загружает комнаты, запускает поиск пиров,
 * инициализирует просмотрщик изображений и динамически подгружает опциональные модули.
 */
window.bootApp = async function bootApp() {
    // PIN lock: if enabled, show lock screen before revealing the app
    if (typeof window._checkPinLock === 'function') {
        await window._checkPinLock();
    }

    $('auth-screen').classList.remove('active');
    $('auth-screen').style.display = 'none';
    $('app').style.display         = 'flex';
    const _btabs = document.getElementById('bottom-tabs');
    if (_btabs) _btabs.style.display = '';

    // Сохраняем текущий аккаунт в список мультиаккаунтов (ключ + данные)
    if (typeof window._saveCurrentAccountOnBoot === 'function') {
        window._saveCurrentAccountOnBoot();
    }

    // Initialize i18n, keyboard shortcuts, accessibility, preferences, network
    await initI18n();
    shortcuts.initShortcuts();
    a11y.initA11y();
    gestures.initGestures();
    preferences.initPreferences();
    netStatus.initNetworkStatus();

    // Заполняем информацию о пользователе в сайдбаре
    const sbAv = $('sb-avatar');
    if (sbAv) {
        if (AppState.user.avatar_url) {
            const img = document.createElement('img');
            img.src = AppState.user.avatar_url;
            img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:50%;';
            sbAv.textContent = '';
            sbAv.appendChild(img);
        } else {
            if (AppState.user.avatar_emoji) { sbAv.textContent = AppState.user.avatar_emoji; }
            else { sbAv.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>'; }
        }
    }
    const sbName = $('sb-name');
    if (sbName) sbName.textContent = AppState.user.display_name || AppState.user.username;
    const sbPhone = $('sb-phone');
    if (sbPhone) sbPhone.textContent = AppState.user.phone;
    updateSidebarStatus();

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

    // Zero-Knowledge: инициализируем ZK ключи из приватного ключа пользователя
    try {
        const privKey = AppState.x25519PrivateKey
            || sessionStorage.getItem('vortex_x25519_priv')
            || localStorage.getItem('vortex_x25519_priv');
        if (privKey) {
            await zkCrypto.initZKKeys(privKey);
            console.log('🔒 ZK crypto initialized');
        }
    } catch (e) {
        console.warn('ZK crypto init failed:', e.message);
    }

    // Настраиваем UI в зависимости от режима сети
    const isGlobal = AppState.user?.network_mode === 'global';
    AppState.networkMode = isGlobal ? 'global' : 'local';

    // Переключаем видимость навигационных элементов по data-mode
    document.querySelectorAll('[data-mode]').forEach(el => {
        const elMode = el.dataset.mode;
        el.style.display = (elMode === 'global') ? (isGlobal ? '' : 'none')
                                                  : (isGlobal ? 'none' : '');
    });

    // Загружаем список комнат, спейсов и начинаем опрос пиров
    skeletons.showRoomsSkeleton();
    await rooms.loadMyRooms();
    skeletons.hideRoomsSkeleton();
    spaces.loadMySpaces();  // async, non-blocking — renders icon bar when ready
    if (!isGlobal) startPeerPolling();

    // Загружаем контакты и избранные IDs
    await contacts.loadContacts();
    saved.loadSavedIds?.();

    // Загружаем сторис (dynamic import — не блокирует приложение при ошибке)
    try {
        const stories = await import('./stories.js');
        Object.assign(window, stories);
        window._storyUserIds = stories.storyUserIds;
        stories.loadStories();
        console.log('📖 stories загружен');
    } catch (e) {
        console.warn('stories.js не загружен:', e.message);
    }
    notifications.connectNotificationWS();
    notifications.startMultiplexCover();

    // Восстанавливаем состояние DND из localStorage
    const dndCheckbox = document.getElementById('set-dnd-enabled');
    if (dndCheckbox) {
        dndCheckbox.checked = notifSounds.isDND();
    }

    // Загружаем статусы контактов
    if (typeof window.loadStatuses === 'function') {
        window.loadStatuses();
    }

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

    // Авто-открытие последней комнаты или приветственный экран
    const lastRoomId = parseInt(localStorage.getItem('vortex_last_room'));
    if (lastRoomId) {
        const lastRoom = AppState.rooms.find(r => r.id === lastRoomId);
        if (lastRoom) {
            openRoom(lastRoomId);
        } else {
            showWelcome();
        }
    } else {
        showWelcome();
    }

    // Подписываемся на Web Push (если разрешено)
    subscribePush();

    // Start cross-device sync polling + initial history migration + auto-backup
    keyBackup.startSyncPolling();
    keyBackup.autoBackupIfNeeded().catch(() => {});

    // BMP: always-on unified transport for all room types
    startBMP();
    // Register BMP secrets for ALL room types: rooms, channels, DMs, federated, spaces
    const _allBmpRooms = [
        ...(window.AppState?.rooms || []),
        ...(window.AppState?.channels || []),
        ...(window.AppState?.dmRooms || []),
        ...(window.AppState?.federatedRooms || []),
    ];
    for (const room of _allBmpRooms) {
        const rid = room.id || room.room_id;
        if (rid) registerRoomSecret(rid).catch(() => {});
    }
    keyBackup.runInitialHistoryMigration().catch(() => {});

    // Onboarding tour for first-time users (0 rooms, never dismissed)
    if (AppState.rooms.length === 0 && !isOnboardingDone()) {
        startOnboarding();
    }

    // Prompt to set up security questions (once, only if not done yet)
    if (!localStorage.getItem('vortex_sq_done')) {
        setTimeout(() => {
            if (typeof window._showSecurityQuestionsSetup === 'function') {
                window._showSecurityQuestionsSetup();
            }
        }, 3000);
    }

    // Monthly password check reminder (every 30 days)
    // On first ever login — set the timestamp so it doesn't trigger immediately
    if (!localStorage.getItem('vortex_pw_check_ts')) {
        localStorage.setItem('vortex_pw_check_ts', String(Date.now()));
    } else {
        const lastPwCheck = parseInt(localStorage.getItem('vortex_pw_check_ts'), 10);
        const daysSince = (Date.now() - lastPwCheck) / 86400000;
        if (daysSince >= 30) {
            setTimeout(() => {
                if (typeof window._showPasswordReminder === 'function') {
                    window._showPasswordReminder();
                }
            }, 5000);
        }
    }

    // Check unseen missed calls and show notification
    try {
        const missedData = await api('GET', '/api/calls/missed/unseen');
        if (missedData.count > 0) {
            const { t: _t } = await import('./i18n.js');
            const n = missedData.count;
            const label = _t('calls.missed');
            if (typeof window.showToast === 'function') {
                window.showToast(`${label}: ${n}`, 'info');
            }
            // Mark as seen
            api('POST', '/api/calls/missed/mark-seen').catch(() => {});
        }
    } catch (e) { console.debug('missed calls check:', e); }
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

// При загрузке страницы загружаем CSRF и проверяем сессию
window.addEventListener('DOMContentLoaded', async () => {
    initLangPicker();
    await loadCsrfToken();
    phonePassword.initPhonePassword();
    checkSession();

    // Обработка QR deep link: vortex://qr-login?s=<session_id>&c=<challenge>&p=<server_pubkey>
    function _handleQRDeepLink(url) {
        try {
            const u = new URL(url);
            if (u.pathname !== '//qr-login' && !url.includes('qr-login')) return;
            const s = u.searchParams.get('s');
            const c = u.searchParams.get('c');
            const p = u.searchParams.get('p');
            if (s && c && p && window.confirmQRLogin) {
                window.confirmQRLogin(s, c, p);
            }
        } catch (_) {}
    }

    // Tauri deep link
    if (window.VortexNative?.isTauri()) {
        window.VortexNative.onDeepLink((url) => _handleQRDeepLink(url));
    }
    // Web: если страница открыта с ?qr=... (PWA share_target или кастомный handler)
    const qrParam = new URLSearchParams(location.search).get('qr');
    if (qrParam) _handleQRDeepLink(decodeURIComponent(qrParam));
});