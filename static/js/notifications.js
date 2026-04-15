// static/js/notifications.js
// ============================================================================
// Уведомления в реальном времени через WebSocket.
// Показывает баннеры при получении новых сообщений в неактивных комнатах.
// ============================================================================

import { $, esc } from './utils.js';
import { playMessageSound, playCallSound, stopCallSound } from './notification-sounds.js';

// Expose stopCallSound for inline onclick handlers in call banners
window._stopCallSound = stopCallSound;

let _notifWs = null;
let _reconnectTimer = null;

// ── Счётчики непрочитанных ──────────────────────────────────────────────────
// { roomId: { count: число, mention: boolean } }
const _unread = {};

export function getUnreadCount(roomId) {
    return _unread[roomId]?.count || 0;
}

export function hasMention(roomId) {
    return _unread[roomId]?.mention || false;
}

export function clearUnread(roomId) {
    delete _unread[roomId];
}

function _incrementUnread(roomId, isMention) {
    if (!_unread[roomId]) _unread[roomId] = { count: 0, mention: false };
    _unread[roomId].count++;
    if (isMention) _unread[roomId].mention = true;
}

// ── WebSocket для уведомлений ────────────────────────────────────────────────

export function connectNotificationWS() {
    if (_notifWs && _notifWs.readyState <= 1) return;

    // Используем тот же протокол что и страница
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    _tryConnect(`${proto}://${location.host}/ws/notifications`);
}

async function _tryConnect(url) {
    // Anti-probing: knock sequence в global mode
    if (window.AppState.user?.network_mode === 'global') {
        try {
            await fetch('/cover/pricing', {credentials: 'include'});
            await fetch('/cover/about', {credentials: 'include'});
        } catch {}
    }
    const knockCookie = document.cookie.split(';').find(c => c.trim().startsWith('_vk='))?.split('=')[1];
    const knockParam = knockCookie ? `${url.includes('?') ? '&' : '?'}knock=${knockCookie}` : '';

    try {
        _notifWs = new WebSocket(`${url}${knockParam}`);
    } catch (e) {
        console.warn('notifications WS error:', e.message);
        _scheduleReconnect();
        return;
    }

    _notifWs.onopen = () => {
        console.log('notifications WS connected:', url);
        if (_reconnectTimer) {
            clearTimeout(_reconnectTimer);
            _reconnectTimer = null;
        }
    };

    _notifWs.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            handleNotification(data);
        } catch {}
    };

    _notifWs.onclose = (e) => {
        _notifWs = null;
        if (e.code === 4401) {
            console.warn('notifications WS: auth failed, retry in 30s');
            _reconnectTimer = setTimeout(() => { _reconnectTimer = null; connectNotificationWS(); }, 30000);
            return;
        }
        _scheduleReconnect();
    };

    _notifWs.onerror = () => {
        _notifWs?.close();
    };
}

export function disconnectNotificationWS() {
    if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
    }
    if (_notifWs) {
        _notifWs.onclose = null;
        _notifWs.close();
        _notifWs = null;
    }
}

function _scheduleReconnect() {
    if (_reconnectTimer) return;
    const delay = 3000 + Math.random() * 12000;  // 3-15 секунд (рандомизация)
    _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null;
        connectNotificationWS();
    }, delay);
}

// ── Обработка уведомлений ────────────────────────────────────────────────────

function handleNotification(data) {
    const S = window.AppState;

    // Новая story — обновляем stories strip
    if (data.type === 'new_story') {
        if (typeof window.loadStories === 'function') window.loadStories();
        return;
    }

    // Story reaction/reply — показываем toast
    if (data.type === 'story_reaction' || data.type === 'story_reply') {
        const name = data.from_display_name || data.from_username || '';
        const text = data.type === 'story_reaction'
            ? `${name} ${data.emoji || '❤️'}`
            : `${name}: ${(data.text || '').slice(0, 50)}`;
        if (typeof window.showToast === 'function') window.showToast(text, 'info');
        return;
    }

    // Новый DM — добавляем комнату в список, показываем уведомление
    if (data.type === 'new_dm' && data.room) {
        _handleNewDm(data);
        return;
    }

    // Запрос ключа комнаты — отвечаем через REST API (store-key)
    // Это позволяет передать ключ даже если мы в другом чате
    if (data.type === 'key_request' && data.room_id) {
        _handleKeyRequestFromNotif(data);
        return;
    }

    // Ключ комнаты доставлен через notification WS
    // (когда получатель подключён к room WS — ключ придёт туда, это fallback)
    if (data.type === 'room_key' && data.room_id) {
        _handleRoomKeyFromNotif(data);
        return;
    }

    // Moderation strike notification — show alert to the user
    if (data.type === 'moderation' && data.action === 'strike') {
        const desc = data.description || '';
        showNotificationBanner({
            type:      'notification',
            room_name: t('notifications.moderation'),
            sender:    t('notifications.strikeNumber', {number: data.strike_number || '?'}),
            text:      desc,
        });
        return;
    }

    // Входящий звонок — показываем специальный баннер и открываем комнату
    if (data.type === 'incoming_call') {
        _handleIncomingCall(data);
        return;
    }

    // Stream scheduled — browser notification
    if (data.type === 'stream_scheduled') {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(data.room_name || 'Vortex', {
                body: '\uD83D\uDCC5 ' + (data.title || 'Live') + ' — ' + (data.scheduled_at || '').replace('T', ' '),
                icon: '/static/icons/icon-192x192.png',
            });
        }
        return;
    }

    // Stream auto-start — scheduled stream time has come, host gets this even from another room
    if (data.type === 'stream_auto_start') {
        const roomId = data.room_id;
        const title = data.title || 'Live';
        // Show confirmation banner and auto-start the stream
        if (typeof window.openRoom === 'function') {
            window.openRoom(roomId);
        }
        // Delay slightly to let room load, then trigger stream start
        setTimeout(async () => {
            try {
                if (typeof window.openStreamSettings === 'function') {
                    // Set state and start directly
                    const { startStreamAuto } = await import('./stream.js');
                    if (typeof startStreamAuto === 'function') {
                        startStreamAuto(roomId, title);
                    }
                }
            } catch (e) {
                console.warn('[Notif] auto-start stream error:', e);
            }
        }, 1500);
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(t('notifications.scheduledStreamStarting'), {
                body: title,
                icon: '/static/icons/icon-192x192.png',
            });
        }
        return;
    }

    // Stream started — browser notification
    if (data.type === 'stream_state' && data.action === 'started') {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(t('notifications.streamStarted'), {
                body: data.room_name || 'Vortex',
                icon: '/static/icons/icon-192x192.png',
            });
        }
        return;
    }

    // Не считаем непрочитанным для текущей активной комнаты
    if (data.room_id && S.currentRoom?.id === data.room_id) return;

    // Инкрементируем счётчик
    if (data.room_id) {
        _incrementUnread(data.room_id, data.is_mention || false);
        // Перерисовываем список комнат чтобы показать бейдж
        if (typeof window.renderRoomsList === 'function') window.renderRoomsList();
    }

    showNotificationBanner(data);
}

async function _handleRoomKeyFromNotif(data) {
    // Ключ пришёл через notification WS (fallback когда room WS уже обработал или нет)
    const S = window.AppState;
    try {
        const { eciesDecrypt, setRoomKey } = await import('./crypto.js');
        const privKey = S.x25519PrivateKey;
        if (!privKey) return;

        const keyBytes = await eciesDecrypt(data.ephemeral_pub, data.ciphertext, privKey);
        setRoomKey(data.room_id, keyBytes);

        // Сохраняем в in-memory cache + sessionStorage
        const { _saveRoomKeyToSession } = await import('./chat/room-crypto.js');
        _saveRoomKeyToSession(data.room_id, keyBytes);
        if (window.registerRoomSecret) window.registerRoomSecret(data.room_id);
        console.info('🔑 Ключ комнаты получен через notification WS, room', data.room_id);

        // Если мы сейчас в этой комнате — перезагружаем историю
        if (S.currentRoom?.id === data.room_id && S.ws?.readyState === WebSocket.OPEN) {
            S.ws.send(JSON.stringify({ action: 'ping' }));  // trigger reconnect effect
            // Проще — переоткрыть комнату
            if (typeof window.openRoom === 'function') window.openRoom(data.room_id);
        }
    } catch (e) {
        console.warn('room_key via notif failed:', e.message);
    }
}

function _handleNewDm(data) {
    const S = window.AppState;
    if (!S.rooms) S.rooms = [];

    const room = data.room;
    room.is_dm = true;
    room.dm_user = data.dm_user;

    // Не добавляем дубликат
    if (S.rooms.find(r => r.id === room.id)) return;

    S.rooms.unshift(room);

    // Перерисовываем список комнат
    if (typeof window.renderRoomsList === 'function') {
        window.renderRoomsList();
    }

    // Показываем баннер-уведомление
    const name = data.dm_user?.display_name || data.dm_user?.username || t('notifications.newChat');
    showNotificationBanner({
        type:      'notification',
        room_id:   room.id,
        room_name: name,
        sender:    name,
        text:      t('notifications.newDirectMessage'),
    });

    console.info('📩 Новый DM от', name, '→ room', room.id);
}

async function _handleKeyRequestFromNotif(data) {
    try {
        // Пытаемся получить ключ из in-memory store или sessionStorage
        const { getRoomKey } = await import('./crypto.js');
        let roomKeyBytes = getRoomKey(data.room_id);
        if (!roomKeyBytes) {
            const hex = sessionStorage.getItem(`vortex_rk_${data.room_id}`);
            if (!hex) {
                console.info('key_request via notif: нет ключа для room', data.room_id);
                return;
            }
            roomKeyBytes = Uint8Array.from(hex.match(/.{2}/g).map(b => parseInt(b, 16)));
        }

        // Шифруем ключ для запрашивающего пользователя
        const { eciesEncrypt } = await import('./crypto.js');
        const enc = await eciesEncrypt(roomKeyBytes, data.for_pubkey);

        // Сохраняем через REST API
        const { api } = await import('./utils.js');
        await api('POST', `/api/dm/store-key/${data.room_id}`, {
            user_id:       data.for_user_id,
            ephemeral_pub: enc.ephemeral_pub,
            ciphertext:    enc.ciphertext,
        });
        console.info('✅ Ключ передан пользователю', data.for_user_id, 'для room', data.room_id);
    } catch (e) {
        console.warn('key_request via notif failed:', e.message);
    }
}

function _handleIncomingCall(data) {
    const callerName = data.caller_display_name || data.caller_username || t('notifications.unknown');
    const callType   = data.has_video ? t('notifications.videoCall') : t('notifications.voiceCall');

    // Показываем баннер звонка (не исчезает автоматически)
    const container = $('notification-container');
    if (!container) return;

    const banner = document.createElement('div');
    banner.className = 'notification-banner call-banner';
    banner.innerHTML = `
        <div class="notif-avatar">${esc(data.caller_avatar || '\u{1F464}')}</div>
        <div class="notif-body">
            <div class="notif-sender">${esc(callerName)}</div>
            <div class="notif-text">${callType}</div>
        </div>
        <button class="btn btn-primary btn-sm" style="background:var(--green);border-color:var(--green);"
                onclick="window._stopCallSound(); this.closest('.notification-banner').remove(); window._answerCallFromNotif(${data.room_id})">
            ${t('notifications.answer')}
        </button>
        <button class="btn btn-secondary btn-sm"
                onclick="window._stopCallSound(); this.closest('.notification-banner').remove()">
            ${t('notifications.decline')}
        </button>
    `;

    container.appendChild(banner);
    requestAnimationFrame(() => banner.classList.add('show'));

    // Воспроизводим рингтон входящего звонка
    playCallSound();

    // Звонок: не автоудаляем — пользователь сам решает
    setTimeout(() => {
        if (banner.parentNode) {
            banner.classList.remove('show');
            setTimeout(() => banner.remove(), 300);
            stopCallSound();
        }
    }, 30000);
}

// Глобальная функция — открыть комнату и подключиться к signal WS для ответа
window._answerCallFromNotif = async function(roomId) {
    const S = window.AppState;
    let room = S.rooms.find(r => r.id === roomId);

    if (!room) {
        // Перезагружаем список комнат/DM
        try {
            const { api } = await import('./utils.js');
            const [roomsData, dmData] = await Promise.allSettled([
                api('GET', '/api/rooms/my'),
                api('GET', '/api/dm/list'),
            ]);
            const localRooms = roomsData.status === 'fulfilled' ? (roomsData.value.rooms || []) : [];
            const dmRooms    = dmData.status    === 'fulfilled' ? (dmData.value.rooms    || []) : [];
            const allDms     = dmRooms.map(dm => ({...dm.room, is_dm: true, dm_user: dm.other_user}));
            S.rooms = [...localRooms, ...allDms, ...S.rooms.filter(r => r.is_federated)];
            room = S.rooms.find(r => r.id === roomId);
        } catch {}
    }

    if (room && typeof window.openRoom === 'function') {
        await window.openRoom(roomId);
    }

    // Подключаемся к signal WS и отправляем ringing — звонящий повторит offer
    try {
        const signalId = room?.signalRoomId ?? roomId;
        if (typeof window.connectSignal === 'function') {
            window.connectSignal(signalId);
        }
        // Помечаем что ожидаем входящий звонок — webrtc.js покажет incoming UI при получении offer
        S._pendingIncomingCall = roomId;
    } catch {}
}

// ── HTTP/2 Multiplex Cover (имитация загрузки SPA-ресурсов) ─────────────────

let _multiplexTimer = null;

export function startMultiplexCover() {
    if (window.AppState.user?.network_mode !== 'global') return;
    stopMultiplexCover();
    _doMultiplexBurst(); // Начальный burst при загрузке
    _scheduleNextBurst();
}

export function stopMultiplexCover() {
    if (_multiplexTimer) {
        clearTimeout(_multiplexTimer);
        _multiplexTimer = null;
    }
}

function _scheduleNextBurst() {
    // Рандомный интервал 15-90 сек (как клики пользователя в веб-приложении)
    const delay = 15000 + Math.random() * 75000;
    _multiplexTimer = setTimeout(() => {
        _doMultiplexBurst();
        _scheduleNextBurst();
    }, delay);
}

function _doMultiplexBurst() {
    // Имитация загрузки SPA-страницы: параллельные запросы к ресурсам
    const resources = [
        '/cover/static/app.js',
        '/cover/static/style.css',
        '/cover/api/data',
        '/cover/api/status',
        '/cover/about',
    ];

    // Выбираем 3-5 случайных ресурсов (как реальная загрузка страницы)
    const count = 3 + Math.floor(Math.random() * 3);
    const selected = resources.sort(() => Math.random() - 0.5).slice(0, count);

    // Параллельный fetch (создаёт паттерн HTTP/2 мультиплексирования)
    selected.forEach(url => {
        fetch(url, { credentials: 'include' }).catch(() => {});
    });
}

// ── Баннер уведомления ───────────────────────────────────────────────────────

export async function showNotificationBanner(data) {
    const container = $('notification-container');
    if (!container) return;

    // Воспроизводим звук уведомления о новом сообщении
    playMessageSound();

    const banner = document.createElement('div');
    banner.className = 'notification-banner';
    banner.innerHTML = `
        <div class="notif-avatar">${esc(data.sender_avatar || '\u{1F464}')}</div>
        <div class="notif-body">
            <div class="notif-sender">${esc(data.sender_display_name || data.sender_username || 'User')}</div>
            <div class="notif-text">${data.is_dm ? t('notifications.dm') : esc(data.room_name || t('notifications.newMessage'))}</div>
        </div>
    `;

    banner.onclick = () => {
        banner.remove();
        const room = window.AppState.rooms.find(r => r.id === data.room_id);
        if (room && typeof window.openRoom === 'function') {
            window.openRoom(room.id);
        }
    };

    container.appendChild(banner);

    // Анимация появления
    requestAnimationFrame(() => banner.classList.add('show'));

    // Автоматическое скрытие через 5 секунд
    setTimeout(() => {
        banner.classList.remove('show');
        setTimeout(() => banner.remove(), 300);
    }, 5000);

    // Системное уведомление через Service Worker (показывается даже при фоновой вкладке)
    if ('Notification' in window && Notification.permission === 'granted' &&
        document.visibilityState !== 'visible') {
        try {
            const reg = await navigator.serviceWorker?.ready;
            if (reg) {
                reg.showNotification(
                    data.sender_display_name || data.sender_username || 'Vortex',
                    {
                        body: data.is_dm ? t('notifications.dm') : (data.room_name || t('notifications.newMessage')),
                        icon: '/static/icons/icon-192.png',
                        tag:  `vortex-${data.room_id}`,
                        data: { room_id: data.room_id },
                    },
                );
            }
        } catch {}
    }
}
