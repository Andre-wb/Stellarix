import { scrollToBottom } from '../utils.js';
import { renderRoomsList, updateRoomMeta } from '../rooms.js';
import { showWelcome } from '../ui.js';
import {
    appendMessage,
    appendFileMessage,
    appendSystemMessage,
    resetMessageState,
} from './messages.js';

const _typers       = {};
let   _typingActive = false;

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
            updateRoomMeta();
            break;

        case 'user_left':
            appendSystemMessage(`${msg.username} покинул чат`);
            updateRoomMeta();
            break;

        case 'typing':
            _showTyping(msg.username, msg.is_typing);
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

        case 'pong':
            break;
    }
}

export function sendMessage() {
    const input = document.getElementById('msg-input');
    const text  = input.value.trim();
    const S     = window.AppState;
    if (!text || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    S.ws.send(JSON.stringify({ action: 'message', text }));
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

    // utils.js — уровнем выше, '../utils.js'
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

    const names = Object.keys(_typers);
    const el    = document.getElementById('typing-indicator');
    if (names.length) {
        el.classList.add('visible');
        document.getElementById('typing-text').textContent =
            names.join(', ') + (names.length === 1 ? ' печатает' : ' печатают');
    } else {
        el.classList.remove('visible');
    }
}

function _updateOnlineList(users) {
    const S = window.AppState;
    if (S.currentRoom) {
        document.getElementById('chat-room-meta').textContent =
            `${S.currentRoom.member_count} участников · ${users.length} онлайн`;
    }
}