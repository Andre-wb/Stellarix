import { esc, fmtTime, fmtDate, fmtSize } from '../utils.js';

let _lastDate     = null;
let _lastSenderId = null;

export function resetMessageState() {
    _lastDate     = null;
    _lastSenderId = null;
}

export function appendMessage(msg) {
    if (msg.msg_type === 'file' || msg.msg_type === 'image') {
        return appendFileMessage({
            sender_id:    msg.sender_id,
            sender:       msg.sender,
            display_name: msg.display_name,
            avatar_emoji: msg.avatar_emoji,
            file_name:    msg.file_name,
            file_size:    msg.file_size,
            mime_type:    _guessMimeFromText(msg.text) || (msg.msg_type === 'image' ? 'image/jpeg' : 'application/octet-stream'),
            download_url: _extractDownloadUrl(msg.text),
            created_at:   msg.created_at,
        });
    }

    const S       = window.AppState;
    const container = document.getElementById('messages-container');
    const isOwn   = msg.sender_id === S.user?.user_id;
    const isPeer  = msg.from_peer;

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
            ${isPeer ? '<span class="msg-peer-badge">P2P</span>' : ''}`;
        group.appendChild(author);
    }

    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${isOwn ? 'own' : ''}`;
    bubble.textContent = msg.text || '';

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

export function appendFileMessage(msg) {
    const S         = window.AppState;
    const container = document.getElementById('messages-container');
    const isOwn     = msg.sender_id === S.user?.user_id;
    const isImage   = msg.mime_type?.startsWith('image/');
    const isVideo   = msg.mime_type?.startsWith('video/');

    const div = document.createElement('div');
    div.className = 'fade-in';

    const authorHtml = `
        <div class="msg-author">
            <div class="msg-avatar">${esc(msg.avatar_emoji || '👤')}</div>
            <span class="msg-name">${esc(msg.display_name || msg.sender || '?')}</span>
            <span class="msg-time">${fmtTime(msg.created_at)}</span>
        </div>`;

    if (isImage && msg.download_url) {
        const safeName = esc(msg.file_name || '').replace(/'/g, "\\'");
        div.innerHTML = `
            ${authorHtml}
            <div class="msg-bubble ${isOwn ? 'own' : ''} msg-bubble-img"
                 onclick="window.openImageViewer('${msg.download_url}','${safeName}')">
                <img src="${msg.download_url}"
                     alt="${esc(msg.file_name || '')}"
                     class="chat-image"
                     loading="lazy"
                     onerror="this.closest('.msg-bubble-img').classList.add('file-msg');this.remove()">
                <div class="chat-image-meta">${esc(msg.file_name || '')} · ${fmtSize(msg.file_size || 0)}</div>
            </div>`;
    } else {
        const icon = isVideo ? '🎬' : msg.mime_type?.startsWith('audio/') ? '🎵' : '📄';
        div.innerHTML = `
            ${authorHtml}
            <div class="msg-bubble ${isOwn ? 'own' : ''} file-msg">
                <span class="file-icon">${icon}</span>
                <div class="file-info">
                    <div class="file-name">${esc(msg.file_name || 'файл')}</div>
                    <div class="file-size">${fmtSize(msg.file_size || 0)}</div>
                </div>
                ${msg.download_url ? `<a class="file-download" href="${msg.download_url}" download>↓ Скачать</a>` : ''}
            </div>`;
    }

    _lastSenderId = msg.sender_id;
    container.appendChild(div);
}

export function appendSystemMessage(text) {
    const div = document.createElement('div');
    div.innerHTML = `<div class="msg-bubble system">${esc(text)}</div>`;
    document.getElementById('messages-container').appendChild(div);
    _lastSenderId = null;
}

function _extractDownloadUrl(text) {
    if (!text) return null;
    const m = text.match(/\[file:(\d+):/);
    return m ? `/api/files/download/${m[1]}` : null;
}

function _guessMimeFromText(text) {
    if (!text) return null;
    const m = text.match(/\[file:\d+:(.+?)\]/);
    if (!m) return null;
    const ext = m[1].split('.').pop().toLowerCase();
    return { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
             gif: 'image/gif', webp: 'image/webp',
             mp4: 'video/mp4', webm: 'video/webm',
             mp3: 'audio/mpeg', ogg: 'audio/ogg', wav: 'audio/wav' }[ext] || null;
}