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

const _typers       = {};
let   _typingActive = false;
const _fileSenders  = {}; // username → filename

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
            break;
    }
}

function _updateOnlineList(users) {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const el = document.getElementById('chat-room-meta');
    if (el) {
        el.textContent = `${S.currentRoom.member_count} участников · ${users.length} онлайн`;
    }
}

let _replyTo   = null;
let _editingId = null;

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
    if (bar) {
        bar.classList.remove('visible');
        delete bar.dataset.mode;
    }
    const input = document.getElementById('msg-input');
    if (input) { input.placeholder = 'Сообщение…'; input.value = ''; }
};

window.startEditMessage = (msg) => {
    _editingId = msg.msg_id;
    _replyTo   = null;
    const bar      = document.getElementById('reply-bar');
    const nameEl   = document.getElementById('reply-bar-name');
    const textEl   = document.getElementById('reply-bar-text');
    if (bar) {
        bar.dataset.mode = 'edit';
        bar.classList.add('visible');
        if (nameEl) nameEl.textContent = '✏️ Редактирование';
        if (textEl) textEl.textContent = _truncate(msg.text || '', 60);
    }
    const input = document.getElementById('msg-input');
    if (input) {
        input.value = msg.text || '';
        input.focus();
    }
};

window.deleteMessage = (msgId) => {
    const S = window.AppState;
    if (!msgId || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    S.ws.send(JSON.stringify({ action: 'delete_message', msg_id: msgId }));
};

function _truncate(str, n) { return str?.length > n ? str.slice(0, n) + '…' : str || ''; }

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
    } catch { }
}

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