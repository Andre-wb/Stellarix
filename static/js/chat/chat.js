// static/js/chat/chat.js
import { scrollToBottom } from '../utils.js';
import { renderRoomsList } from '../rooms.js';
import { eciesDecrypt, eciesEncrypt, getRoomKey, setRoomKey } from '../crypto.js';
import { showWelcome } from '../ui.js';
import {
    appendMessage,
    appendFileMessage,
    appendSystemMessage,
    resetMessageState,
    deleteMessageAnim,
    updateMessageText,
} from './messages.js';

const _typers       = {};
let   _typingActive = false;
const _fileSenders  = {};

let _replyTo   = null;
let _editingId = null;

let _pendingHistory = null;

// ─── ACK-система ──────────────────────────────────────────────────────────────
const _pendingAcks = new Map();

const ACK_TIMEOUT_MS = 4000;
const ACK_MAX_RETRY  = 3;

const _offlineQueue = [];

// =============================================================================
// AES-256-GCM утилиты
// =============================================================================

const toHex   = b => Array.from(new Uint8Array(b)).map(x => x.toString(16).padStart(2,'0')).join('');
const fromHex = h => Uint8Array.from(h.match(/.{2}/g).map(b => parseInt(b, 16)));

async function encryptText(text, roomKeyBytes) {
    const key = await crypto.subtle.importKey(
        'raw', roomKeyBytes, { name: 'AES-GCM' }, false, ['encrypt']
    );
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ct    = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv: nonce },
        key,
        new TextEncoder().encode(text)
    );
    return toHex(nonce) + toHex(ct);
}

async function decryptText(ciphertextHex, roomKeyBytes) {
    const raw   = fromHex(ciphertextHex);
    const nonce = raw.slice(0, 12);
    const ct    = raw.slice(12);
    const key   = await crypto.subtle.importKey(
        'raw', roomKeyBytes, { name: 'AES-GCM' }, false, ['decrypt']
    );
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, key, ct);
    return new TextDecoder().decode(plain);
}

// =============================================================================
// Хранение ключа комнаты в sessionStorage
// =============================================================================

function _saveRoomKeyToSession(roomId, keyBytes) {
    try { sessionStorage.setItem(`vortex_rk_${roomId}`, toHex(keyBytes)); } catch {}
}

function _loadRoomKeyFromSession(roomId) {
    try {
        const hex = sessionStorage.getItem(`vortex_rk_${roomId}`);
        return hex ? fromHex(hex) : null;
    } catch { return null; }
}

function _clearRoomKeyFromSession(roomId) {
    try { sessionStorage.removeItem(`vortex_rk_${roomId}`); } catch {}
}

// =============================================================================
// ACK-система — гарантированная доставка сообщений
// =============================================================================

export function sendWithAck(payload) {
    const msgId = crypto.randomUUID();
    payload     = { ...payload, msg_id: msgId };

    return new Promise((resolve, reject) => {
        _pendingAcks.set(msgId, {
            payload,
            retries:   0,
            timeoutId: null,
            resolve,
            reject,
        });
        _trySend(msgId);
    });
}

function _trySend(msgId) {
    const entry = _pendingAcks.get(msgId);
    if (!entry) return;

    const S  = window.AppState;
    const ws = S.ws;

    if (!ws || ws.readyState !== WebSocket.OPEN) {
        if (!_offlineQueue.find(m => m.msg_id === msgId)) {
            _offlineQueue.push(entry.payload);
        }
        return;
    }

    ws.send(JSON.stringify(entry.payload));

    entry.timeoutId = setTimeout(() => {
        const e = _pendingAcks.get(msgId);
        if (!e) return;

        if (e.retries < ACK_MAX_RETRY) {
            e.retries++;
            console.warn(`[ACK] retry ${e.retries}/${ACK_MAX_RETRY} для ${msgId}`);
            _trySend(msgId);
        } else {
            _pendingAcks.delete(msgId);
            e.reject(new Error(`Сообщение не доставлено после ${ACK_MAX_RETRY} попыток`));
            appendSystemMessage('⚠️ Сообщение не было доставлено. Проверьте соединение.');
        }
    }, ACK_TIMEOUT_MS);
}

function _handleAck(msg) {
    const entry = _pendingAcks.get(msg.msg_id);
    if (!entry) return;

    clearTimeout(entry.timeoutId);
    _pendingAcks.delete(msg.msg_id);
    entry.resolve(msg.server_id ?? msg.msg_id);
    console.debug(`[ACK] подтверждён ${msg.msg_id} → server_id=${msg.server_id}`);
}

function _cancelAllPendingAcks() {
    for (const [msgId, entry] of _pendingAcks) {
        clearTimeout(entry.timeoutId);
        _pendingAcks.delete(msgId);
        entry.reject(new Error('Соединение закрыто'));
    }
}

function _flushOfflineQueue() {
    const S = window.AppState;
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) return;

    while (_offlineQueue.length > 0) {
        const payload = _offlineQueue.shift();
        const msgId   = payload.msg_id;

        if (msgId && _pendingAcks.has(msgId)) {
            _trySend(msgId);
        } else {
            try { S.ws.send(JSON.stringify(payload)); } catch {}
        }
    }
}

// =============================================================================
// WebSocket — управление соединением
// =============================================================================

let _msgQueue = Promise.resolve();

export function connectWS(roomId) {
    const S = window.AppState;

    if (S.ws) {
        if (S.ws._ping) clearInterval(S.ws._ping);
        S.ws.onclose = null;
        S.ws.close();
        S.ws = null;
    }

    _pendingHistory  = null;
    _cancelAllPendingAcks();

    const cachedKey = _loadRoomKeyFromSession(roomId);
    if (cachedKey) {
        setRoomKey(roomId, cachedKey);
        console.info('🔑 Ключ комнаты восстановлен из sessionStorage для room', roomId);
    }

    const proto  = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsPath = S.currentRoom?.is_federated ? `/ws/fed/${roomId}` : `/ws/${roomId}`;
    S.ws      = new WebSocket(`${proto}://${location.host}${wsPath}`);
    _msgQueue = Promise.resolve();

    S.ws.onopen = () => {
        console.log('WS connected, room', roomId);
        _flushOfflineQueue();
    };

    S.ws.onmessage = e => {
        const data = JSON.parse(e.data);
        _msgQueue  = _msgQueue
            .then(() => handleWsMessage(data))
            .catch(err => console.error('WS msg error:', err));
    };

    S.ws.onclose = e => {
        if (e.code === 4401) { window.doLogout(); return; }
        if (e.code === 4403) { alert('Нет доступа к комнате'); return; }
        if (S.currentRoom?.id === roomId)
            setTimeout(() => connectWS(roomId), 3000);
    };

    S.ws._ping = setInterval(() => {
        if (S.ws?.readyState === WebSocket.OPEN)
            S.ws.send(JSON.stringify({ action: 'ping' }));
    }, 25000);
}

async function handleWsMessage(msg) {
    const S = window.AppState;
    switch (msg.type) {

        case 'ack':
            _handleAck(msg);
            break;

        case 'room_key': {
            const privKey = S.x25519PrivateKey;
            const roomId  = msg.room_id ?? S.currentRoom?.id;
            if (!roomId) { console.warn('room_key: нет roomId'); break; }
            if (!privKey) {
                appendSystemMessage(
                    '🔑 Не удалось расшифровать ключ комнаты: приватный ключ не найден. ' +
                    'Воспользуйтесь кнопкой «Импорт ключа» в профиле.'
                );
                break;
            }
            try {
                const keyBytes = await eciesDecrypt(msg.ephemeral_pub, msg.ciphertext, privKey);
                setRoomKey(roomId, keyBytes);
                _saveRoomKeyToSession(roomId, keyBytes);
                console.info('🔑 Ключ комнаты получен и сохранён, room', roomId);

                if (_pendingHistory) {
                    const pendingMessages = _pendingHistory;
                    _pendingHistory = null;
                    resetMessageState();
                    document.getElementById('messages-container').innerHTML = '';
                    for (const m of pendingMessages) await _decryptAndAppend(m);
                    scrollToBottom();
                }
            } catch (e) {
                appendSystemMessage('🔑 Ошибка расшифровки ключа комнаты: ' + e.message);
            }
            break;
        }

        case 'key_request': {
            const roomId  = S.currentRoom?.id;
            const roomKey = getRoomKey(roomId);
            if (!roomKey) break;
            try {
                const enc = await eciesEncrypt(roomKey, msg.for_pubkey);
                S.ws.send(JSON.stringify({
                    action:        'key_response',
                    for_user_id:   msg.for_user_id,
                    ephemeral_pub: enc.ephemeral_pub,
                    ciphertext:    enc.ciphertext,
                }));
            } catch (e) { console.error('Ошибка re-encryption:', e); }
            break;
        }

        case 'waiting_for_key':
            appendSystemMessage('⏳ Ожидание ключа комнаты от другого участника...');
            break;

        case 'node_pubkey':
            S.nodePublicKey = msg.pubkey_hex;
            break;

        case 'history': {
            const roomKey = getRoomKey(S.currentRoom?.id);
            if (!roomKey && msg.messages?.length) {
                _pendingHistory = msg.messages;
                resetMessageState();
                document.getElementById('messages-container').innerHTML = '';
                appendSystemMessage('⏳ Ожидание ключа комнаты для расшифровки истории...');
            } else {
                _pendingHistory = null;
                resetMessageState();
                document.getElementById('messages-container').innerHTML = '';
                for (const m of msg.messages) await _decryptAndAppend(m);
                scrollToBottom();
            }
            break;
        }

        case 'signal':
            if (typeof window.handleFederatedSignal === 'function')
                window.handleFederatedSignal(msg);
            break;

        case 'message':
        case 'peer_message': {
            // ── FIX: дедупликация — не рендерим если это наш ACK-ожидаемый
            // client_msg_id, который уже есть в _pendingAcks (ещё не подтверждён).
            // ACK придёт отдельно и разрешит промис. Само сообщение рендерим
            // только когда сервер прислал его как broadcast (т.е. оно уже в БД).
            //
            // НО: если ACK уже обработан (_pendingAcks не содержит этот id),
            // значит broadcast пришёл позже ACK или это чужое сообщение — рендерим.
            //
            // Итого: рендерим ВСЕГДА, но пропускаем если для этого client_msg_id
            // ещё висит pending ACK (значит мы уже знаем что отправили, и
            // рендер произойдёт когда ACK придёт и снимет ожидание... нет,
            // без оптимистичного рендера нам нужен broadcast).
            //
            // Правильная логика: сервер теперь шлёт broadcast ВСЕМ включая
            // отправителя. Отправитель получает и ACK и message. ACK — для
            // подтверждения записи в БД. message — для рендера. Рендерим
            // message всегда. Чтобы не было дубля — проверяем DOM.
            if (msg.client_msg_id) {
                const existing = document.querySelector(
                    `[data-client-msg-id="${CSS.escape(msg.client_msg_id)}"]`
                );
                if (existing) break; // уже отрендерено (оптимистично или ранее)
            }
            await _decryptAndAppend(msg);
            scrollToBottom(true);
            break;
        }

        case 'file':
            appendFileMessage(msg);
            scrollToBottom(true);
            break;

        case 'online':
            _updateOnlineList(msg.users);
            break;

        case 'user_joined':
            appendSystemMessage(`${msg.display_name || msg.username} вошёл в чат`);
            if (msg.online_users) _updateOnlineList(msg.online_users);
            break;

        case 'user_left':
            appendSystemMessage(`${msg.username} покинул чат`);
            if (msg.online_users) _updateOnlineList(msg.online_users);
            break;

        case 'typing':
            _showTyping(msg.username, msg.is_typing);
            break;

        case 'file_sending':
            _showFileSending(msg.display_name || msg.username, msg.filename);
            break;

        case 'stop_file_sending':
            _showFileSending(msg.sender, null);
            break;

        case 'kicked':
            alert('Вы были исключены из комнаты');
            _clearRoomKeyFromSession(S.currentRoom?.id);
            S.rooms = S.rooms.filter(r => r.id !== S.currentRoom?.id);
            renderRoomsList();
            showWelcome();
            break;

        case 'room_deleted':
            alert('Комната была удалена');
            _clearRoomKeyFromSession(S.currentRoom?.id);
            S.rooms = S.rooms.filter(r => r.id !== S.currentRoom?.id);
            renderRoomsList();
            showWelcome();
            break;

        case 'system':
            appendSystemMessage(msg.text);
            break;

        case 'message_deleted':
            deleteMessageAnim(msg.msg_id);
            break;

        case 'message_edited':
            await _decryptAndUpdateMessage(msg);
            break;

        case 'error':
            if (msg.code !== 'rate_limited') {
                console.warn('[WS error]', msg.message);
            } else {
                appendSystemMessage('⏱ Слишком быстро. Подождите немного.');
            }
            break;

        case 'pong':
            break;
    }
}

async function _decryptAndAppend(msg) {
    const S       = window.AppState;
    const roomKey = getRoomKey(S.currentRoom?.id);

    if (msg.ciphertext) {
        if (roomKey) {
            try { msg.text = await decryptText(msg.ciphertext, roomKey); }
            catch { msg.text = '[ошибка расшифровки]'; }
        } else {
            msg.text = '[🔒 зашифровано — ключ не получен]';
        }
    }
    if (msg.reply_to_id && !msg.reply_to_text) {
        const cached = window._msgTexts?.get(msg.reply_to_id);
        if (cached) {
            msg.reply_to_text   = cached.text;
            msg.reply_to_sender = cached.sender;
        }
    }
    appendMessage(msg);
}

async function _decryptAndUpdateMessage(msg) {
    const S       = window.AppState;
    const roomKey = getRoomKey(S.currentRoom?.id);
    let   text    = '[ошибка расшифровки]';
    if (roomKey && msg.ciphertext) {
        try { text = await decryptText(msg.ciphertext, roomKey); } catch {}
    }
    updateMessageText(msg.msg_id, text, msg.is_edited);
}

function _updateOnlineList(users) {
    const S  = window.AppState;
    const el = document.getElementById('chat-room-meta');
    if (el && S.currentRoom)
        el.textContent = `${S.currentRoom.member_count} участников · ${users.length} онлайн`;
}

// =============================================================================
// Reply / Edit
// =============================================================================

window.setReplyTo = (msg) => {
    _replyTo   = msg;
    _editingId = null;
    const bar  = document.getElementById('reply-bar');
    const name = document.getElementById('reply-bar-name');
    const text = document.getElementById('reply-bar-text');
    if (bar) {
        bar.classList.add('visible');
        if (name) name.textContent = msg.display_name || msg.sender || '?';
        if (text) text.textContent = _truncate(msg.text || msg.file_name || 'файл', 60);
    }
    document.getElementById('msg-input')?.focus();
};

window.cancelReply = () => {
    _replyTo   = null;
    _editingId = null;
    const bar = document.getElementById('reply-bar');
    if (bar) { bar.classList.remove('visible'); delete bar.dataset.mode; }
    const input = document.getElementById('msg-input');
    if (input) { input.placeholder = 'Сообщение…'; input.value = ''; }
};

window.startEditMessage = (msg) => {
    _editingId = msg.msg_id;
    _replyTo   = null;
    const bar    = document.getElementById('reply-bar');
    const nameEl = document.getElementById('reply-bar-name');
    const textEl = document.getElementById('reply-bar-text');
    if (bar) {
        bar.dataset.mode = 'edit';
        bar.classList.add('visible');
        if (nameEl) nameEl.textContent = '✏️ Редактирование';
        if (textEl) textEl.textContent = _truncate(msg.text || '', 60);
    }
    const input = document.getElementById('msg-input');
    if (input) { input.value = msg.text || ''; input.focus(); }
};

window.deleteMessage = (msgId) => {
    const S = window.AppState;
    if (!msgId || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    S.ws.send(JSON.stringify({ action: 'delete_message', msg_id: msgId }));
};

function _truncate(str, n) { return str?.length > n ? str.slice(0, n) + '…' : str || ''; }

// =============================================================================
// Отправка сообщений (с ACK)
// =============================================================================

export async function sendMessage() {
    const input   = document.getElementById('msg-input');
    const text    = input.value.trim();
    const S       = window.AppState;
    if (!text) return;

    const roomKey = getRoomKey(S.currentRoom?.id);

    if (_editingId) {
        if (!roomKey) {
            appendSystemMessage('⚠️ Нет ключа комнаты — сообщение не отправлено');
            return;
        }
        const ciphertext = await encryptText(text, roomKey);
        S.ws?.send(JSON.stringify({ action: 'edit_message', msg_id: _editingId, ciphertext }));
        _editingId = null;
        const bar = document.getElementById('reply-bar');
        if (bar) { bar.classList.remove('visible'); delete bar.dataset.mode; }
    } else {
        if (!roomKey) {
            appendSystemMessage('⚠️ Ключ комнаты не получен. Дождитесь подключения другого участника.');
            return;
        }
        const ciphertext = await encryptText(text, roomKey);
        const payload    = { action: 'message', ciphertext };
        if (_replyTo?.msg_id) payload.reply_to_id = _replyTo.msg_id;

        sendWithAck(payload).catch(err => {
            console.error('[ACK] не доставлено:', err.message);
        });

        _replyTo = null;
        const bar2 = document.getElementById('reply-bar');
        if (bar2) { bar2.classList.remove('visible'); delete bar2.dataset.mode; }
    }

    input.value = '';
    input.style.height = 'auto';
}

export function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

export function handleTyping() {
    const input = document.getElementById('msg-input');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';

    const S = window.AppState;
    if (!_typingActive && S.ws?.readyState === WebSocket.OPEN) {
        _typingActive = true;
        S.ws.send(JSON.stringify({ action: 'typing', is_typing: true }));
    }
    clearTimeout(S.typingTimeout);
    S.typingTimeout = setTimeout(() => {
        _typingActive = false;
        S.ws?.send(JSON.stringify({ action: 'typing', is_typing: false }));
    }, 2000);
}

// =============================================================================
// Файлы
// =============================================================================

export async function showRoomFilesModal() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const { openModal, api, esc, fmtSize: _fmtSize } = await import('../utils.js');
    openModal('files-modal');
    const el = document.getElementById('files-list');
    el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text2);">Загрузка...</div>';
    try {
        const data = await api('GET', `/api/files/room/${S.currentRoom.id}`);
        el.innerHTML = data.files.length
            ? data.files.map(f => {
                const isImage  = f.mime_type?.startsWith('image/');
                const icon     = isImage ? '🖼' : f.mime_type?.startsWith('video/') ? '🎬'
                    : f.mime_type?.startsWith('audio/') ? '🎵' : '📄';
                const safeName = esc(f.file_name).replace(/'/g, "\\'");
                return `
                <div style="padding:10px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;">
                    <span style="font-size:24px;">${icon}</span>
                    <div style="flex:1;min-width:0;">
                        <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(f.file_name)}</div>
                        <div style="font-size:11px;color:var(--text2);font-family:var(--mono);">${_fmtSize(f.size_bytes)} · ${f.uploader}</div>
                        ${f.file_hash ? `<div style="font-size:10px;color:var(--text3);font-family:var(--mono);">SHA-256: ${f.file_hash.slice(0,16)}…</div>` : ''}
                    </div>
                    ${isImage ? `<span style="cursor:pointer;font-size:16px;color:var(--accent2);"
                        onclick="closeModal('files-modal');window.openImageViewer('${f.download_url}','${safeName}')">🔍</span>` : ''}
                    <a href="${f.download_url}" download class="btn btn-secondary btn-sm">↓</a>
                </div>`;
            }).join('')
            : '<div style="padding:24px;text-align:center;color:var(--text2);">Файлов нет</div>';
    } catch {}
}

// =============================================================================
// Индикаторы набора текста и отправки файла
// =============================================================================

function _showTyping(username, isTyping) {
    if (isTyping) _typers[username] = true;
    else delete _typers[username];
    _renderTypingBar();
}

function _showFileSending(username, filename) {
    if (filename) _fileSenders[username] = filename;
    else          delete _fileSenders[username];
    _renderTypingBar();
}

function _renderTypingBar() {
    const typers = Object.keys(_typers);
    const filers = Object.entries(_fileSenders);
    const el     = document.getElementById('typing-indicator');
    const textEl = document.getElementById('typing-text');
    const parts  = [];
    if (typers.length)
        parts.push(typers.join(', ') + (typers.length === 1 ? ' печатает' : ' печатают'));
    filers.forEach(([name, fname]) => {
        const short = fname.length > 24 ? fname.slice(0, 22) + '…' : fname;
        parts.push(`${name} отправляет файл «${short}»`);
    });
    if (parts.length) {
        el.classList.add('visible');
        textEl.textContent = parts.join(' · ');
    } else {
        el.classList.remove('visible');
    }
}

export function getAckStats() {
    return {
        pending:       _pendingAcks.size,
        offlineQueue:  _offlineQueue.length,
    };
}