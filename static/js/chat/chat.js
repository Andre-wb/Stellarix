// static/js/chat/chat.js
// =============================================================================
// Модуль управления WebSocket-соединением чата.
// Обрабатывает входящие сообщения, управляет состоянием набора текста,
// отправкой файлов, ответами на сообщения, редактированием/удалением.
// =============================================================================

import { scrollToBottom } from '../utils.js';
import { renderRoomsList, updateRoomMeta } from '../rooms.js';
import { showWelcome } from '../ui.js';
import {
    appendMessage,
    appendFileMessage,
    appendSystemMessage,
    resetMessageState,
    deleteMessageAnim,
    updateMessageText,
} from './messages.js';

// Хранилище текущих печатающих пользователей и отправителей файлов
const _typers       = {};
let   _typingActive = false; // флаг, что текущий пользователь печатает (для предотвращения спама)
const _fileSenders  = {}; // username → filename

// Текущие цели для ответа и редактирования
let _replyTo   = null;
let _editingId = null;

// =============================================================================
// Управление WebSocket
// =============================================================================

/**
 * Устанавливает WebSocket-соединение для указанной комнаты.
 * Настраивает обработчики onopen, onmessage, onclose.
 * Запускает периодический ping для поддержания соединения.
 *
 * @param {string} roomId - ID комнаты
 */
export function connectWS(roomId) {
    const S     = window.AppState;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    S.ws        = new WebSocket(`${proto}://${location.host}/ws/${roomId}`);

    S.ws.onopen = () => console.log('WS connected, room', roomId);

    S.ws.onmessage = e => {
        try { handleWsMessage(JSON.parse(e.data)); }
        catch (err) { console.error('WS parse error:', err); }
    };

    S.ws.onclose = e => {
        if (e.code === 4401) { window.doLogout(); return; }           // неавторизован
        if (e.code === 4403) { alert('Нет доступа к комнате'); return; }
        if (S.currentRoom?.id === roomId)
            setTimeout(() => connectWS(roomId), 3000); // попытка переподключения
    };

    // Пинг каждые 25 секунд, чтобы держать соединение открытым
    S.ws._ping = setInterval(() => {
        if (S.ws?.readyState === WebSocket.OPEN)
            S.ws.send(JSON.stringify({ action: 'ping' }));
    }, 25000);
}

/**
 * Обрабатывает входящее сообщение WebSocket (JSON).
 * В зависимости от типа вызывает соответствующие функции обновления UI.
 *
 * @param {Object} msg - распарсенный объект сообщения
 */
function handleWsMessage(msg) {
    const S = window.AppState;
    switch (msg.type) {
        case 'node_pubkey':
            S.nodePublicKey = msg.pubkey_hex;
            break;

        case 'history':
            resetMessageState();
            document.getElementById('messages-container').innerHTML = '';
            msg.messages.forEach(m => appendMessage(m));
            scrollToBottom();
            break;

        case 'message':
        case 'peer_message':
            appendMessage(msg);
            scrollToBottom(true);
            break;

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
            S.rooms = S.rooms.filter(r => r.id !== S.currentRoom?.id);
            renderRoomsList();
            showWelcome();
            break;

        case 'room_deleted':
            alert('Комната была удалена');
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
            updateMessageText(msg.msg_id, msg.text, msg.is_edited);
            break;

        case 'pong':
            // игнорируем
            break;
    }
}

/**
 * Обновляет счётчик участников и онлайн в шапке комнаты.
 *
 * @param {Array} users - список онлайн-пользователей
 */
function _updateOnlineList(users) {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const el = document.getElementById('chat-room-meta');
    if (el) {
        el.textContent = `${S.currentRoom.member_count} участников · ${users.length} онлайн`;
    }
}

// =============================================================================
// Управление ответами и редактированием (глобальные функции, вызываемые из messages.js)
// =============================================================================

/**
 * Устанавливает режим «ответить» на указанное сообщение.
 * Показывает панель reply-bar с именем и текстом исходного сообщения.
 * @param {Object} msg - сообщение, на которое отвечаем
 */
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

/**
 * Отменяет режим ответа или редактирования (скрывает панель, сбрасывает цели).
 */
window.cancelReply = () => {
    _replyTo   = null;
    _editingId = null;
    const bar = document.getElementById('reply-bar');
    if (bar) {
        bar.classList.remove('visible');
        delete bar.dataset.mode;
    }
    const input = document.getElementById('msg-input');
    if (input) { input.placeholder = 'Сообщение…'; input.value = ''; }
};

/**
 * Устанавливает режим «редактировать» для указанного сообщения.
 * Заполняет поле ввода текстом сообщения, меняет заголовок панели.
 * @param {Object} msg - сообщение для редактирования
 */
window.startEditMessage = (msg) => {
    _editingId = msg.msg_id;
    _replyTo   = null;
    const bar      = document.getElementById('reply-bar');
    const nameEl   = document.getElementById('reply-bar-name');
    const textEl   = document.getElementById('reply-bar-text');
    if (bar) {
        bar.dataset.mode = 'edit';
        bar.classList.add('visible');
        if (nameEl) nameEl.innerHTML = '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" > <path d="M19.67 2.61c-.81-.81-2.14-.81-2.95 0L3.38 15.95c-.13.13-.22.29-.26.46l-1.09 4.34c-.08.34.01.7.26.95.19.19.45.29.71.29.08 0 .16 0 .24-.03l4.34-1.09c.18-.04.34-.13.46-.26L21.38 7.27c.81-.81.81-2.14 0-2.95L19.66 2.6ZM6.83 19.01l-2.46.61.61-2.46 9.96-9.94 1.84 1.84zM19.98 5.86 18.2 7.64 16.36 5.8l1.78-1.78s.09-.03.12 0l1.72 1.72s.03.09 0 .12"></path></svg> Редактирование';
        if (textEl) textEl.textContent = _truncate(msg.text || '', 60);
    }
    const input = document.getElementById('msg-input');
    if (input) {
        input.value = msg.text || '';
        input.focus();
    }
};

/**
 * Отправляет запрос на удаление сообщения.
 * @param {string} msgId - идентификатор сообщения
 */
window.deleteMessage = (msgId) => {
    const S = window.AppState;
    if (!msgId || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    S.ws.send(JSON.stringify({ action: 'delete_message', msg_id: msgId }));
};

/**
 * Усекает строку до n символов, добавляя многоточие.
 */
function _truncate(str, n) { return str?.length > n ? str.slice(0, n) + '…' : str || ''; }

// =============================================================================
// Отправка сообщений
// =============================================================================

/**
 * Отправляет сообщение (или редактирование) через WebSocket.
 * Считывает текст из поля ввода, учитывает режимы reply/edit.
 */
export function sendMessage() {
    const input = document.getElementById('msg-input');
    const text  = input.value.trim();
    const S     = window.AppState;
    if (!text || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;

    if (_editingId) {
        S.ws.send(JSON.stringify({ action: 'edit_message', msg_id: _editingId, text }));
        _editingId = null;
        const bar = document.getElementById('reply-bar');
        if (bar) { bar.classList.remove('visible'); delete bar.dataset.mode; }
    } else {
        const payload = { action: 'message', text };
        if (_replyTo?.msg_id) payload.reply_to_id = _replyTo.msg_id;
        S.ws.send(JSON.stringify(payload));
        _replyTo = null;
        const bar2 = document.getElementById('reply-bar');
        if (bar2) { bar2.classList.remove('visible'); delete bar2.dataset.mode; }
    }

    input.value = '';
    input.style.height = 'auto';
}

/**
 * Обработчик нажатия клавиш в поле ввода.
 * Enter (без Shift) отправляет сообщение.
 *
 * @param {KeyboardEvent} e
 */
export function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

/**
 * Обработчик ввода текста (отслеживание набора).
 * Автоматически изменяет высоту textarea, отправляет статус typing на сервер.
 */
export function handleTyping() {
    const input = document.getElementById('msg-input');
    // Автоподстройка высоты под контент (до 120px)
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';

    const S = window.AppState;
    if (!_typingActive && S.ws?.readyState === WebSocket.OPEN) {
        _typingActive = true;
        S.ws.send(JSON.stringify({ action: 'typing', is_typing: true }));
    }
    clearTimeout(S.typingTimeout);
    // Через 2 секунды бездействия снимаем статус печати
    S.typingTimeout = setTimeout(() => {
        _typingActive = false;
        S.ws?.send(JSON.stringify({ action: 'typing', is_typing: false }));
    }, 2000);
}

// =============================================================================
// Модальное окно со списком файлов комнаты
// =============================================================================

/**
 * Открывает модальное окно со списком всех файлов текущей комнаты.
 * Загружает данные через API и рендерит их.
 */
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
                    </div>
                    ${isImage ? `<span style="cursor:pointer;font-size:16px;color:var(--accent2);"
                        onclick="closeModal('files-modal');window.openImageViewer('${f.download_url}','${safeName}')">🔍</span>` : ''}
                    <a href="${f.download_url}" download class="btn btn-secondary btn-sm">↓</a>
                </div>`;
            }).join('')
            : '<div style="padding:24px;text-align:center;color:var(--text2);">Файлов нет</div>';
    } catch { /* ошибка загрузки — ничего не делаем, остаётся заглушка */ }
}

// =============================================================================
// Отображение статусов печати и отправки файлов
// =============================================================================

/**
 * Обновляет словарь печатающих пользователей и вызывает перерисовку индикатора.
 *
 * @param {string} username
 * @param {boolean} isTyping
 */
function _showTyping(username, isTyping) {
    if (isTyping) _typers[username] = true;
    else delete _typers[username];
    _renderTypingBar();
}

/**
 * Обновляет словарь отправляющих файлы пользователей и вызывает перерисовку.
 *
 * @param {string} username
 * @param {string|null} filename - null означает, что отправка завершена
 */
function _showFileSending(username, filename) {
    if (filename) _fileSenders[username] = filename;
    else          delete _fileSenders[username];
    _renderTypingBar();
}

/**
 * Рендерит нижнюю панель с индикацией печатающих и отправляющих файлы.
 * Собирает информацию из _typers и _fileSenders и формирует текст.
 */
function _renderTypingBar() {
    const typers  = Object.keys(_typers);
    const filers  = Object.entries(_fileSenders);
    const el      = document.getElementById('typing-indicator');
    const textEl  = document.getElementById('typing-text');

    const parts = [];
    if (typers.length)
        parts.push(typers.join(', ') + (typers.length === 1 ? ' печатает' : ' печатают'));
    if (filers.length) {
        filers.forEach(([name, fname]) => {
            const short = fname.length > 24 ? fname.slice(0, 22) + '…' : fname;
            parts.push(`${name} отправляет файл «${short}»`);
        });
    }

    if (parts.length) {
        el.classList.add('visible');
        textEl.textContent = parts.join(' · ');
    } else {
        el.classList.remove('visible');
    }
}