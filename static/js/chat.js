import { $, api, esc, fmtTime, fmtDate, fmtSize, scrollToBottom, openModal, closeModal, getCookie } from './utils.js';
import { renderRoomsList, updateRoomMeta } from './rooms.js';
import { showWelcome } from './ui.js';

let _lastDate = null;
let _lastSenderId = null;
let _typingActive = false;
const _typers = {};
let _pendingFile = null;

export function connectWS(roomId) {
    const S = window.AppState;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws/${roomId}`;
    S.ws = new WebSocket(url);

    S.ws.onopen = () => {
        console.log('WS connected, room', roomId);
    };

    S.ws.onmessage = e => {
        const msg = JSON.parse(e.data);
        handleWsMessage(msg);
    };

    S.ws.onclose = e => {
        if (e.code === 4401) { window.doLogout(); return; }
        if (e.code === 4403) { alert('Нет доступа к комнате'); return; }
        if (S.currentRoom?.id === roomId) {
            setTimeout(() => connectWS(roomId), 3000);
        }
    };

    S.ws._ping = setInterval(() => {
        if (S.ws?.readyState === WebSocket.OPEN) S.ws.send(JSON.stringify({ action: 'ping' }));
    }, 25000);
}

function handleWsMessage(msg) {
    const S = window.AppState;
    switch (msg.type) {
        case 'node_pubkey':
            S.nodePublicKey = msg.pubkey_hex;
            break;
        case 'history':
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
            updateOnlineList(msg.users);
            break;
        case 'user_joined':
        case 'user_left':
            appendSystemMessage(msg.type === 'user_joined'
                ? `${msg.display_name || msg.username} вошёл в чат`
                : `${msg.username} покинул чат`);
            updateRoomMeta();
            break;
        case 'typing':
            showTyping(msg.username, msg.is_typing);
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

function appendMessage(msg) {
    const S = window.AppState;
    const container = $('messages-container');
    const isOwn = msg.sender_id === S.user?.user_id;
    const isPeer = msg.from_peer;

    const date = fmtDate(msg.created_at || new Date().toISOString());
    if (date !== _lastDate) {
        _lastDate = date;
        const div = document.createElement('div');
        div.className = 'date-divider';
        div.textContent = date;
        container.appendChild(div);
        _lastSenderId = null;
    }

    const showAuthor = msg.sender_id !== _lastSenderId;
    _lastSenderId = msg.sender_id;

    const group = document.createElement('div');
    group.className = 'fade-in';

    if (showAuthor && !isOwn) {
        const author = document.createElement('div');
        author.className = 'msg-author';
        author.innerHTML = `
      <div class="msg-avatar">${esc(msg.avatar_emoji || '👤')}</div>
      <span class="msg-name">${esc(msg.display_name || msg.sender || '?')}</span>
      <span class="msg-time">${fmtTime(msg.created_at)}</span>
      ${isPeer ? '<span class="msg-peer-badge">P2P</span>' : ''}
    `;
        group.appendChild(author);
    }

    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${isOwn ? 'own' : ''}`;
    bubble.innerHTML = esc(msg.text || '');

    if (isOwn) {
        const timeEl = document.createElement('div');
        timeEl.style.cssText = 'font-size:10px;color:var(--text3);margin-top:3px;text-align:right;font-family:var(--mono);';
        timeEl.textContent = fmtTime(msg.created_at);
        group.appendChild(bubble);
        group.appendChild(timeEl);
    } else {
        group.appendChild(bubble);
    }

    container.appendChild(group);
}

function appendFileMessage(msg) {
    const S = window.AppState;
    const container = $('messages-container');
    const isOwn = msg.sender_id === S.user?.user_id;
    const div = document.createElement('div');
    div.className = 'fade-in';

    const isImage = msg.mime_type?.startsWith('image/');
    const isVideo = msg.mime_type?.startsWith('video/');

    if (isImage) {
        div.innerHTML = `
      <div class="msg-author">
        <div class="msg-avatar">${esc(msg.avatar_emoji || '👤')}</div>
        <span class="msg-name">${esc(msg.display_name || msg.sender)}</span>
        <span class="msg-time">${fmtTime(msg.created_at)}</span>
      </div>
      <div class="msg-bubble ${isOwn ? 'own' : ''} msg-bubble-img"
           onclick="window.openImageViewer('${msg.download_url}', '${esc(msg.file_name).replace(/'/g,"\\'")}')">
        <img src="${msg.download_url}" alt="${esc(msg.file_name)}"
             class="chat-image"
             onerror="this.parentElement.classList.add('file-msg');this.remove()">
        <div class="chat-image-meta">${esc(msg.file_name)} · ${fmtSize(msg.file_size)}</div>
      </div>
    `;
    } else {
        const icon = isVideo ? '🎬' : msg.mime_type?.startsWith('audio/') ? '🎵' : '📄';
        div.innerHTML = `
      <div class="msg-author">
        <div class="msg-avatar">${esc(msg.avatar_emoji || '👤')}</div>
        <span class="msg-name">${esc(msg.display_name || msg.sender)}</span>
        <span class="msg-time">${fmtTime(msg.created_at)}</span>
      </div>
      <div class="msg-bubble ${isOwn ? 'own' : ''} file-msg">
        <span class="file-icon">${icon}</span>
        <div class="file-info">
          <div class="file-name">${esc(msg.file_name)}</div>
          <div class="file-size">${fmtSize(msg.file_size)}</div>
        </div>
        <a class="file-download" href="${msg.download_url}" download>↓ Скачать</a>
      </div>
    `;
    }

    container.appendChild(div);
}

function appendSystemMessage(text) {
    const div = document.createElement('div');
    div.innerHTML = `<div class="msg-bubble system">${esc(text)}</div>`;
    $('messages-container').appendChild(div);
    _lastSenderId = null;
}

export function sendMessage() {
    const input = $('msg-input');
    const text = input.value.trim();
    const S = window.AppState;
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
    const input = $('msg-input');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    const S = window.AppState;
    if (!_typingActive && S.ws?.readyState === WebSocket.OPEN) {
        _typingActive = true;
        S.ws.send(JSON.stringify({ action: 'typing', is_typing: true }));
    }
    clearTimeout(window.AppState.typingTimeout);
    window.AppState.typingTimeout = setTimeout(() => {
        _typingActive = false;
        S.ws?.send(JSON.stringify({ action: 'typing', is_typing: false }));
    }, 2000);
}

function showTyping(username, isTyping) {
    if (isTyping) _typers[username] = true;
    else delete _typers[username];
    const names = Object.keys(_typers);
    const el = $('typing-indicator');
    if (names.length) {
        el.classList.add('visible');
        $('typing-text').textContent = names.join(', ') + (names.length === 1 ? ' печатает' : ' печатают');
    } else {
        el.classList.remove('visible');
    }
}

function updateOnlineList(users) {
    const S = window.AppState;
    if (S.currentRoom) {
        $('chat-room-meta').textContent = `${S.currentRoom.member_count} участников · ${users.length} онлайн`;
    }
}

export function triggerFileUpload() {
    $('file-input').click();
}

export function uploadFile(e) {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;

    _pendingFile = file;
    const isImage = file.type.startsWith('image/');

    _resetUploadState();

    if (isImage) {
        const reader = new FileReader();
        reader.onload = ev => {
            $('preview-img').src = ev.target.result;
            $('preview-img').style.display = 'block';
            $('preview-file-card').style.display = 'none';
            $('preview-filename').textContent = file.name;
            $('preview-filesize').textContent = fmtSize(file.size);
            $('file-preview-overlay').classList.add('show');
        };
        reader.readAsDataURL(file);
    } else {
        const icon = file.type.startsWith('video/') ? '🎬'
            : file.type.startsWith('audio/') ? '🎵' : '📄';
        $('preview-img').style.display = 'none';
        $('preview-file-card').style.display = 'flex';
        $('preview-file-icon').textContent = icon;
        $('preview-file-name').textContent = file.name;
        $('preview-file-size').textContent = fmtSize(file.size);
        $('preview-filename').textContent = file.name;
        $('preview-filesize').textContent = fmtSize(file.size);
        $('file-preview-overlay').classList.add('show');
    }
}

export function cancelFilePreview() {
    // Не даём отменить во время загрузки
    if ($('file-preview-overlay').classList.contains('uploading')) return;
    _pendingFile = null;
    $('file-preview-overlay').classList.remove('show');
    $('preview-img').src = '';
    _resetUploadState();
}

export async function sendPendingFile() {
    if (!_pendingFile) return;
    const S = window.AppState;
    if (!S.currentRoom?.id) return;

    const file = _pendingFile;
    const csrfToken = S.csrfToken || getCookie('csrf_token');
    if (!csrfToken) {
        _showUploadError('CSRF токен не найден. Обновите страницу.');
        return;
    }

    // ── Переводим UI в состояние загрузки ──────────────────────────────────
    _setUploadingState(true);

    const formData = new FormData();
    formData.append('file', file);
    // CSRF также в заголовке — основной канал проверки после BUG-001 fix
    // Поле в теле оставляем для совместимости со старыми клиентами

    try {
        const response = await fetch(`/api/files/upload/${S.currentRoom.id}`, {
            method: 'POST',
            credentials: 'include',
            // BUG-001 FIX (клиентская сторона): X-CSRF-Token в заголовке —
            // это единственный способ передать токен для multipart без
            // того чтобы добавлять его в тело (что раньше и вызывало зависание).
            headers: { 'X-CSRF-Token': csrfToken },
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || err.error || `Ошибка сервера (HTTP ${response.status})`);
        }

        // ── Успех: показываем галочку, затем закрываем ──────────────────────
        _showUploadSuccess(() => {
            _pendingFile = null;
            $('file-preview-overlay').classList.remove('show');
            $('preview-img').src = '';
            _resetUploadState();
        });

    } catch (err) {
        // ── Ошибка: разблокируем UI и показываем сообщение ─────────────────
        _setUploadingState(false);
        _showUploadError(err.message);
    }
}

// ─── Вспомогательные функции состояния upload UI ────────────────────────────

function _setUploadingState(uploading) {
    const overlay  = $('file-preview-overlay');
    const sendBtn  = $('preview-send-btn');
    const cancelBtn = overlay.querySelector('.fpo-cancel-btn');

    if (uploading) {
        overlay.classList.add('uploading');
        sendBtn.disabled = true;
        sendBtn.classList.add('btn-uploading');
        sendBtn.innerHTML = '<span class="upload-spinner"></span>Загрузка...';
        if (cancelBtn) { cancelBtn.disabled = true; cancelBtn.style.opacity = '0.4'; }
    } else {
        overlay.classList.remove('uploading');
        sendBtn.disabled = false;
        sendBtn.classList.remove('btn-uploading');
        sendBtn.innerHTML = '↑ Отправить';
        if (cancelBtn) { cancelBtn.disabled = false; cancelBtn.style.opacity = ''; }
    }
}

function _showUploadSuccess(callback) {
    const sendBtn = $('preview-send-btn');
    sendBtn.innerHTML = '✓ Отправлено';
    sendBtn.classList.add('btn-success');
    setTimeout(callback, 600);
}

function _showUploadError(message) {
    // Показываем ошибку в fpo-bar под кнопками
    let errEl = $('fpo-upload-error');
    if (!errEl) {
        errEl = document.createElement('div');
        errEl.id = 'fpo-upload-error';
        errEl.className = 'fpo-upload-error';
        $('file-preview-overlay').querySelector('.fpo-bar').appendChild(errEl);
    }
    errEl.textContent = '⚠ ' + message;
    errEl.classList.add('show');
    // Скрываем через 5 секунд
    clearTimeout(errEl._hideTimer);
    errEl._hideTimer = setTimeout(() => errEl.classList.remove('show'), 5000);
}

function _resetUploadState() {
    const overlay = $('file-preview-overlay');
    if (!overlay) return;
    overlay.classList.remove('uploading');
    const sendBtn = $('preview-send-btn');
    if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.classList.remove('btn-uploading', 'btn-success');
        sendBtn.innerHTML = '↑ Отправить';
    }
    const errEl = $('fpo-upload-error');
    if (errEl) errEl.classList.remove('show');
}

export function openImageViewer(url, name) {
    $('image-viewer-img').src = url;
    $('image-viewer-name').textContent = name;
    $('image-viewer-overlay').classList.add('show');
}

export function closeImageViewer() {
    $('image-viewer-overlay').classList.remove('show');
    $('image-viewer-img').src = '';
}

export async function showRoomFilesModal() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    openModal('files-modal');
    const el = $('files-list');
    el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text2);">Загрузка...</div>';
    try {
        const data = await api('GET', `/api/files/room/${S.currentRoom.id}`);
        el.innerHTML = data.files.length ? data.files.map(f => {
            const isImage = f.mime_type?.startsWith('image/');
            const icon = isImage ? '🖼' : f.mime_type?.startsWith('video/') ? '🎬'
                : f.mime_type?.startsWith('audio/') ? '🎵' : '📄';
            const safeName = esc(f.file_name).replace(/'/g, "\\'");
            return `
        <div style="padding:10px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;">
          <span style="font-size:24px;">${icon}</span>
          <div style="flex:1;min-width:0;">
            <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(f.file_name)}</div>
            <div style="font-size:11px;color:var(--text2);font-family:var(--mono);">${fmtSize(f.size_bytes)} · ${f.uploader}</div>
          </div>
          ${isImage ? `<span style="cursor:pointer;font-size:16px;color:var(--accent2);" onclick="closeModal('files-modal');window.openImageViewer('${f.download_url}','${safeName}')">🔍</span>` : ''}
          <a href="${f.download_url}" download class="btn btn-secondary btn-sm">↓</a>
        </div>
      `;
        }).join('') : '<div style="padding:24px;text-align:center;color:var(--text2);">Файлов нет</div>';
    } catch { }
}