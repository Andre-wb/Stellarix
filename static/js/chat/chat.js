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
                const icon     = isImage ? '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">\n' +
                    '  <path stroke-linecap="round" stroke-linejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />\n' +
                    '</svg>\n' : f.mime_type?.startsWith('video/') ? '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">\n' +
                    '  <path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />\n' +
                    '</svg>\n'
                    : f.mime_type?.startsWith('audio/') ? '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">\n' +
                        '  <path stroke-linecap="round" stroke-linejoin="round" d="M12 18.75a6 6 0 0 0 6-6v-1.5m-6 7.5a6 6 0 0 1-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v8.25a3 3 0 0 1-3 3Z" />\n' +
                        '</svg>\n' : '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">\n' +
                        '  <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />\n' +
                        '</svg>\n';
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