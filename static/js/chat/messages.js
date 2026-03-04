import { esc, fmtTime, fmtDate, fmtSize } from '../utils.js';
import { initLiquidGlass, createReplyQuote } from './liquid-glass.js';

const _SVG_PLAY  = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><path d="M15.5 12L10 15.5V8.5L15.5 12Z" fill="currentColor"/></svg>`;
const _SVG_PAUSE = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><rect x="9" y="8" width="2.2" height="8" rx="1" fill="currentColor"/><rect x="12.8" y="8" width="2.2" height="8" rx="1" fill="currentColor"/></svg>`;

const _ICON_REPLY  = '/static/elements/reply-svgrepo-com.svg';
const _ICON_EDIT   = '/static/elements/edit-svgrepo-com.svg';
const _ICON_DELETE = '/static/elements/delete-2-svgrepo-com.svg';

let _lastDate     = null;
let _lastSenderId = null;

const _msgElements = new Map();

function _ensureContextMenuStyles() {
    if (document.getElementById('ctx-menu-style')) return;
    initLiquidGlass();

    const s = document.createElement('style');
    s.id = 'ctx-menu-style';
    s.textContent = `
    .ctx-backdrop {
        position: fixed;
        inset: 0;
        z-index: 9990;
        background: transparent;
    }

    .ctx-menu {
        position: fixed;
        z-index: 9999;
        min-width: 180px;
        border-radius: 14px;
        padding: 6px 0;
        overflow: hidden;
        animation: ctxFadeIn .14s ease;
    }
    @keyframes ctxFadeIn {
        from { opacity: 0; transform: scale(.92) translateY(-6px); }
        to   { opacity: 1; transform: scale(1)  translateY(0); }
    }

    .ctx-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 11px 16px;
        cursor: pointer;
        transition: background .12s;
        position: relative;
        z-index: 3;
        user-select: none;
        font-size: 14px;
        font-weight: 500;
        color: rgba(255, 255, 255, 0.88);
        letter-spacing: 0.01em;
    }
    .ctx-item:hover {
        background: rgba(255, 255, 255, 0.08);
    }
    .ctx-item:active {
        background: rgba(255, 255, 255, 0.14);
    }
    .ctx-item.danger {
        color: rgba(255, 90, 90, 0.90);
    }
    .ctx-item img {
        width: 18px;
        height: 18px;
        opacity: 0.78;
        filter: invert(1) brightness(1.2);
        flex-shrink: 0;
    }
    .ctx-item.danger img {
        filter: invert(35%) sepia(90%) saturate(500%) hue-rotate(320deg) brightness(1.1);
    }
    .ctx-divider {
        height: 1px;
        margin: 4px 12px;
        background: rgba(255, 255, 255, 0.10);
        position: relative;
        z-index: 3;
    }

    .msg-bubble {
        user-select: text;
        border-radius: 14px;
        padding: 10px 14px;
        max-width: 480px;
        width: fit-content;
        cursor: pointer;
    }
    .msg-bubble.own {
        margin-left: auto;
    }

    .msg-bubble .lg-reply {
        margin-bottom: 6px;
    }
    `;
    document.head.appendChild(s);
}

function _showContextMenu(e, msg, isOwn) {
    e.stopPropagation();

    _closeContextMenu();

    const menu = document.createElement('div');
    menu.className = 'ctx-menu lg';

    const grain = document.createElement('div');
    grain.className = 'lg-grain';
    menu.appendChild(grain);

    const items = [];

    items.push({ icon: _ICON_REPLY, label: 'Ответить', danger: false, action: () => window.setReplyTo(msg) });

    if (isOwn && (!msg.msg_type || msg.msg_type === 'text')) {
        items.push({ icon: _ICON_EDIT, label: 'Редактировать', danger: false, action: () => window.startEditMessage(msg) });
    }

    if (isOwn) {
        items.push({ divider: true });
        items.push({ icon: _ICON_DELETE, label: 'Удалить', danger: true, action: () => window.deleteMessage(msg.msg_id) });
    }

    items.forEach(item => {
        if (item.divider) {
            const d = document.createElement('div');
            d.className = 'ctx-divider';
            menu.appendChild(d);
            return;
        }
        const btn = document.createElement('div');
        btn.className = `ctx-item${item.danger ? ' danger' : ''}`;
        btn.innerHTML = `<img src="${item.icon}" alt=""><span>${item.label}</span>`;
        btn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            _closeContextMenu();
            item.action();
        });
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);

    const bubbleEl = e.currentTarget || e.target.closest('.msg-bubble') || e.target;
    const rect = bubbleEl.getBoundingClientRect
        ? bubbleEl.getBoundingClientRect()
        : { left: e.clientX, top: e.clientY, right: e.clientX, bottom: e.clientY };

    const mw = 190, mh = items.length * 44;
    let x, y;

    if (isOwn) {
        x = rect.left - mw - 8;
        if (x < 8) x = rect.right + 8;
    } else {
        x = rect.right + 8;
        if (x + mw > window.innerWidth - 8) x = rect.left - mw - 8;
    }

    y = rect.top;
    if (y + mh > window.innerHeight - 8) y = window.innerHeight - mh - 8;
    if (y < 8) y = 8;

    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';

    const backdrop = document.createElement('div');
    backdrop.className = 'ctx-backdrop';
    backdrop.id = 'ctx-backdrop';
    backdrop.addEventListener('click', _closeContextMenu);
    document.body.insertBefore(backdrop, menu);
}

function _closeContextMenu() {
    document.getElementById('ctx-backdrop')?.remove();
    document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
}

function _buildReplyQuote(replyToId, replyToText, replyToSender, isOwn = false) {
    const quote = createReplyQuote(
        replyToSender || '?',
        _truncate(replyToText, 80),
        isOwn,
        () => _scrollToMsg(replyToId)
    );
    return quote;
}

export function resetMessageState() {
    _lastDate     = null;
    _lastSenderId = null;
    _msgElements.clear();
}

export function appendMessage(msg) {
    _ensureContextMenuStyles();

    if (msg.msg_type === 'file' || msg.msg_type === 'image' || msg.msg_type === 'voice') {
        return appendFileMessage({
            sender_id:    msg.sender_id,
            sender:       msg.sender,
            display_name: msg.display_name,
            avatar_emoji: msg.avatar_emoji,
            file_name:    msg.file_name,
            file_size:    msg.file_size,
            msg_id:       msg.msg_id,
            msg_type:     msg.msg_type,
            mime_type:    msg.mime_type
                || _guessMimeFromName(msg.file_name)
                || _guessMimeFromText(msg.text)
                || (msg.msg_type === 'image' ? 'image/jpeg' : 'application/octet-stream'),
            download_url: msg.download_url || _extractDownloadUrl(msg.text),
            created_at:   msg.created_at,
            reply_to_id:     msg.reply_to_id,
            reply_to_text:   msg.reply_to_text,
            reply_to_sender: msg.reply_to_sender,
        });
    }

    const S         = window.AppState;
    const container = document.getElementById('messages-container');
    const isOwn     = msg.sender_id === S.user?.user_id;

    const date = fmtDate(msg.created_at || new Date().toISOString());
    if (date !== _lastDate) {
        _lastDate = date;
        const div = document.createElement('div');
        div.className   = 'date-divider';
        div.textContent = date;
        container.appendChild(div);
        _lastSenderId = null;
    }

    const showAuthor = msg.sender_id !== _lastSenderId;
    _lastSenderId = msg.sender_id;

    const group = document.createElement('div');
    group.className        = 'fade-in msg-group';
    group.dataset.msgId    = msg.msg_id || '';
    group.dataset.senderId = msg.sender_id || '';

    if (showAuthor && !isOwn) {
        const author = document.createElement('div');
        author.className = 'msg-author';
        author.innerHTML = `
            <div class="msg-avatar">${esc(msg.avatar_emoji || '👤')}</div>
            <span class="msg-name">${esc(msg.display_name || msg.sender || '?')}</span>
            <span class="msg-time">${fmtTime(msg.created_at)}</span>
            ${msg.from_peer ? '<span class="msg-peer-badge">P2P</span>' : ''}`;
        group.appendChild(author);
    }

    const bubble = document.createElement('div');
    bubble.className = `msg-bubble lg${isOwn ? ' lg-own own' : ''}`;

    const grain = document.createElement('div');
    grain.className = 'lg-grain';
    bubble.appendChild(grain);

    if (msg.reply_to_id && msg.reply_to_text) {
        bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
    }

    const textEl = document.createElement('span');
    textEl.className   = 'msg-text';
    textEl.textContent = msg.text || '';
    bubble.appendChild(textEl);

    if (msg.is_edited) {
        const ed = document.createElement('span');
        ed.className   = 'msg-edited-mark';
        ed.textContent = ' ред.';
        bubble.appendChild(ed);
    }

    bubble.addEventListener('click', (e) => {
        if (e.target.closest('.lg-reply')) return;
        _showContextMenu(e, msg, isOwn);
    });

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
    if (msg.msg_id) _msgElements.set(msg.msg_id, group);
}

export function appendFileMessage(msg) {
    _ensureContextMenuStyles();

    const S         = window.AppState;
    const container = document.getElementById('messages-container');
    const isOwn     = msg.sender_id === S.user?.user_id;

    const mime    = msg.mime_type || _guessMimeFromName(msg.file_name) || 'application/octet-stream';
    const isImage = mime.startsWith('image/');
    const isVideo = mime.startsWith('video/');
    const isAudio = mime.startsWith('audio/');

    const isVoice = msg.msg_type === 'voice'
        || msg.file_name?.startsWith('voice_')
        || (isAudio && (msg.file_name?.includes('voice') || msg.msg_type === 'voice'));

    const div = document.createElement('div');
    div.className        = 'fade-in msg-group';
    div.dataset.msgId    = msg.msg_id || '';
    div.dataset.senderId = msg.sender_id || '';

    const authorHtml = `
        <div class="msg-author">
            <div class="msg-avatar">${esc(msg.avatar_emoji || '👤')}</div>
            <span class="msg-name">${esc(msg.display_name || msg.sender || '?')}</span>
            <span class="msg-time">${fmtTime(msg.created_at)}</span>
        </div>`;

    if (isVoice && msg.download_url) {
        div.innerHTML = authorHtml;
        const vb = _buildVoiceBubble(msg, isOwn);
        div.appendChild(vb);
    } else if (isImage && msg.download_url) {
        /* ── Картинка через liquid glass ── */
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble msg-bubble-img lg${isOwn ? ' lg-own own' : ''}`;

        const grain = document.createElement('div');
        grain.className = 'lg-grain';
        bubble.appendChild(grain);

        if (msg.reply_to_id && msg.reply_to_text) {
            bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
        }

        const img = document.createElement('img');
        img.src       = msg.download_url;
        img.alt       = esc(msg.file_name || '');
        img.className = 'chat-image';
        img.loading   = 'lazy';
        img.onerror   = function() { this.closest('.msg-bubble-img').classList.add('file-msg'); this.remove(); };
        img.onclick   = () => window.openImageViewer(msg.download_url, msg.file_name || '');

        const meta = document.createElement('div');
        meta.className   = 'chat-image-meta';
        meta.textContent = `${esc(msg.file_name || '')} · ${fmtSize(msg.file_size || 0)}`;

        bubble.appendChild(img);
        bubble.appendChild(meta);
        bubble.addEventListener('click', (e) => {
            if (e.target === img || e.target.closest('.lg-reply')) return;
            _showContextMenu(e, msg, isOwn);
        });

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    } else {
        const icon = isVideo ? '🎬' : isAudio ? '🎵' : '📄';

        const bubble = document.createElement('div');
        bubble.className = `msg-bubble file-msg lg${isOwn ? ' lg-own own' : ''}`;

        const grain = document.createElement('div');
        grain.className = 'lg-grain';
        bubble.appendChild(grain);

        if (msg.reply_to_id && msg.reply_to_text) {
            bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
        }

        const fileContent = document.createElement('div');
        fileContent.style.cssText = 'display:flex;align-items:center;gap:12px;position:relative;z-index:4;';
        fileContent.innerHTML = `
            <span class="file-icon">${icon}</span>
            <div class="file-info">
                <div class="file-name">${esc(msg.file_name || 'файл')}</div>
                <div class="file-size">${fmtSize(msg.file_size || 0)}</div>
            </div>
            ${msg.download_url ? `<a class="file-download" href="${msg.download_url}" download>↓ Скачать</a>` : ''}`;
        bubble.appendChild(fileContent);

        bubble.addEventListener('click', (e) => {
            if (e.target.closest('.lg-reply') || e.target.closest('.file-download')) return;
            _showContextMenu(e, msg, isOwn);
        });

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    }

    _lastSenderId = msg.sender_id;
    container.appendChild(div);
    if (msg.msg_id) _msgElements.set(msg.msg_id, div);

    if (isVoice && msg.download_url) {
        _initVoiceBubble(div.querySelector('.vb-wrap'));
    }
}

export function appendSystemMessage(text) {
    const div = document.createElement('div');
    div.innerHTML = `<div class="msg-bubble system">${esc(text)}</div>`;
    document.getElementById('messages-container').appendChild(div);
    _lastSenderId = null;
}

export function deleteMessageAnim(msgId) {
    const el = _msgElements.get(msgId);
    if (!el) return;

    const bubble = el.querySelector('.msg-bubble');
    if (!bubble) { el.remove(); _msgElements.delete(msgId); return; }

    const rect  = bubble.getBoundingClientRect();
    const text  = bubble.innerText.slice(0, 20) || '···';
    const COUNT = 16;

    const layer = document.createElement('div');
    layer.style.cssText = `position:fixed;inset:0;pointer-events:none;z-index:9999;overflow:hidden;`;
    document.body.appendChild(layer);

    for (let i = 0; i < COUNT; i++) {
        const p = document.createElement('span');
        p.textContent = text[i % text.length];
        const x   = rect.left + Math.random() * rect.width;
        const y   = rect.top  + Math.random() * rect.height;
        const dx  = (Math.random() - 0.5) * 140;
        const dy  = (Math.random() - 0.85) * 90;
        const rot = (Math.random() - 0.5) * 720;
        p.style.cssText = `
            position:fixed;left:${x}px;top:${y}px;
            font-size:${11 + Math.random() * 7}px;
            color:var(--accent2);font-weight:700;
            opacity:1;pointer-events:none;user-select:none;
            transition:transform .65s cubic-bezier(.2,0,.8,1),opacity .65s ease;`;
        layer.appendChild(p);
        requestAnimationFrame(() => requestAnimationFrame(() => {
            p.style.transform = `translate(${dx}px,${dy}px) rotate(${rot}deg) scale(.15)`;
            p.style.opacity   = '0';
        }));
    }

    bubble.style.transition = 'transform .35s ease, opacity .35s ease';
    bubble.style.transform  = 'scale(0.05)';
    bubble.style.opacity    = '0';

    setTimeout(() => {
        layer.remove();
        el.style.cssText += 'transition:max-height .3s ease,opacity .3s ease,margin .3s ease;max-height:' + el.offsetHeight + 'px;overflow:hidden;';
        requestAnimationFrame(() => {
            el.style.maxHeight = '0';
            el.style.opacity   = '0';
            el.style.margin    = '0';
        });
        setTimeout(() => { el.remove(); _msgElements.delete(msgId); }, 350);
    }, 650);
}

export function updateMessageText(msgId, newText, isEdited) {
    const el = _msgElements.get(msgId);
    if (!el) return;
    const textEl = el.querySelector('.msg-text');
    if (textEl) textEl.textContent = newText;
    let edMark = el.querySelector('.msg-edited-mark');
    if (isEdited && !edMark) {
        edMark = document.createElement('span');
        edMark.className   = 'msg-edited-mark';
        edMark.textContent = ' ред.';
        const bubble = el.querySelector('.msg-bubble');
        if (bubble) bubble.appendChild(edMark);
    }
    const bubble = el.querySelector('.msg-bubble');
    if (bubble) {
        bubble.classList.add('msg-edited-flash');
        setTimeout(() => bubble.classList.remove('msg-edited-flash'), 700);
    }
}


function _ensureVoiceStyles() {
    if (document.getElementById('vb-style')) return;
    const s = document.createElement('style');
    s.id = 'vb-style';
    s.textContent = `
    /* Layout голосового пузыря — стекло от .lg из liquid-glass */
    .vb-wrap {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 10px 14px;
        border-radius: 16px;
        max-width: 300px;
        min-width: 230px;
        width: fit-content;
    }
    .vb-wrap.own {
        margin-left: auto;
    }
    .vb-wrap > * { position: relative; z-index: 4; }
    .vb-row { display: flex; align-items: center; gap: 12px; }
    .vb-play {
        width: 40px; height: 40px; border-radius: 50%; border: none; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        background: rgba(255, 255, 255, 0.14); color: #fff; cursor: pointer;
        box-shadow: 0 2px 8px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.22);
        transition: transform .12s;
        position: relative; z-index: 4;
    }
    .vb-play:hover  { transform: scale(1.08); }
    .vb-play:active { transform: scale(.94); }
    .vb-play.played { background: rgba(180,180,195,0.18); color: rgba(255,255,255,0.45); }
    .vb-wrap.own .vb-play { background: rgba(195,160,255,0.20); }

    .vb-right { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; position: relative; z-index: 4; }
    .vb-bars  { display: flex; align-items: center; gap: 2px; height: 32px; cursor: pointer; }
    .vb-bar   {
        flex: 1; border-radius: 2px; min-width: 2px;
        background: rgba(200, 215, 240, 0.22);
        transition: background .1s;
    }
    .vb-bar.played { background: rgba(200, 215, 240, 0.72); }
    .vb-bar.done   { background: rgba(175, 180, 195, 0.20); }
    .vb-wrap.own .vb-bar        { background: rgba(195, 168, 255, 0.22); }
    .vb-wrap.own .vb-bar.played { background: rgba(210, 190, 255, 0.72); }
    .vb-wrap.own .vb-bar.done   { background: rgba(175, 170, 195, 0.20); }
    .vb-time {
        font-size: 11px;
        font-family: var(--mono, monospace);
        color: rgba(255, 255, 255, 0.38);
        align-self: flex-end;
        position: relative; z-index: 4;
    }
    `;
    document.head.appendChild(s);
}

function _normPeaks(peaks, N) {
    if (!peaks?.length) {
        return Array.from({ length: N }, (_, i) => 0.2 + (((i * 7 + 3) % 17) / 17) * 0.65);
    }
    const out = [];
    for (let i = 0; i < N; i++) {
        const s = Math.floor(i * peaks.length / N);
        const e = Math.max(s + 1, Math.floor((i + 1) * peaks.length / N));
        let mx = 0;
        for (let j = s; j < e; j++) mx = Math.max(mx, peaks[j] || 0);
        out.push(mx);
    }
    const max = Math.max(...out, 0.01);
    return out.map(v => v / max);
}

function _buildVoiceBubble(msg, isOwn) {
    _ensureVoiceStyles();

    let peaks = null;
    if (msg.file_name) {
        try { peaks = JSON.parse(sessionStorage.getItem('vp:' + msg.file_name) || 'null'); } catch {}
    }

    const BARS      = 40;
    const normPeaks = _normPeaks(peaks, BARS);

    const wrap = document.createElement('div');
    wrap.className   = `vb-wrap lg${isOwn ? ' lg-own own' : ''}`;
    wrap.dataset.src = msg.download_url;

    const grain = document.createElement('div');
    grain.className = 'lg-grain';
    wrap.appendChild(grain);

    if (msg.reply_to_id && msg.reply_to_text) {
        wrap.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
    }

    const row = document.createElement('div');
    row.className = 'vb-row';

    const playBtn = document.createElement('button');
    playBtn.className = 'vb-play';
    playBtn.innerHTML = _SVG_PLAY;

    const right = document.createElement('div');
    right.className = 'vb-right';

    const barsEl = document.createElement('div');
    barsEl.className = 'vb-bars';
    normPeaks.forEach(h => {
        const b = document.createElement('div');
        b.className  = 'vb-bar';
        b.style.height = Math.max(12, h * 100) + '%';
        barsEl.appendChild(b);
    });

    const timeEl = document.createElement('span');
    timeEl.className   = 'vb-time';
    timeEl.textContent = '0:00';

    right.appendChild(barsEl);
    right.appendChild(timeEl);
    row.appendChild(playBtn);
    row.appendChild(right);
    wrap.appendChild(row);

    wrap._playBtn = playBtn;
    wrap._barsEl  = barsEl;
    wrap._timeEl  = timeEl;

    wrap.addEventListener('click', (e) => {
        if (e.target.closest('.vb-play') || e.target.closest('.vb-bars') || e.target.closest('.lg-reply')) return;
        _showContextMenu(e, msg, isOwn);
    });

    return wrap;
}

function _initVoiceBubble(el) {
    if (!el?.dataset?.src) return;
    const audio    = new Audio(el.dataset.src);
    el._audio      = audio;
    const barNodes = el._barsEl ? Array.from(el._barsEl.children) : [];
    const N        = barNodes.length;
    let   done     = false;

    audio.addEventListener('loadedmetadata', () => {
        if (el._timeEl) el._timeEl.textContent = _fmtDur(audio.duration);
    });
    audio.addEventListener('timeupdate', () => {
        if (done) return;
        const pct    = audio.duration ? audio.currentTime / audio.duration : 0;
        const played = Math.round(pct * N);
        barNodes.forEach((b, i) => b.classList.toggle('played', i < played));
        if (el._timeEl) el._timeEl.textContent = _fmtDur(audio.currentTime);
    });
    audio.addEventListener('ended', () => {
        done = true;
        if (el._playBtn) { el._playBtn.innerHTML = _SVG_PLAY; el._playBtn.classList.add('played'); }
        barNodes.forEach(b => { b.classList.remove('played'); b.classList.add('done'); });
        if (el._timeEl && audio.duration) el._timeEl.textContent = _fmtDur(audio.duration);
    });

    if (el._barsEl) {
        el._barsEl.addEventListener('click', e => {
            if (!audio.duration) return;
            const r = el._barsEl.getBoundingClientRect();
            audio.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * audio.duration;
            if (done) {
                done = false;
                if (el._playBtn) el._playBtn.classList.remove('played');
                barNodes.forEach(b => b.classList.remove('done'));
            }
        });
    }

    if (el._playBtn) {
        el._playBtn.onclick = () => {
            if (audio.paused) {
                document.querySelectorAll('.vb-wrap').forEach(b => {
                    if (b !== el && b._audio && !b._audio.paused) {
                        b._audio.pause();
                        if (b._playBtn) b._playBtn.innerHTML = _SVG_PLAY;
                    }
                });
                if (done) {
                    done = false;
                    el._playBtn.classList.remove('played');
                    barNodes.forEach(b => b.classList.remove('done'));
                }
                audio.play().catch(() => {});
                el._playBtn.innerHTML = _SVG_PAUSE;
            } else {
                audio.pause();
                el._playBtn.innerHTML = _SVG_PLAY;
            }
        };
    }
}

window.toggleVoicePlay = () => {};

function _scrollToMsg(msgId) {
    const el = _msgElements.get(msgId);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('msg-highlight');
    setTimeout(() => el.classList.remove('msg-highlight'), 1500);
}
window._scrollToMsg = _scrollToMsg;

function _truncate(str, n) { return str?.length > n ? str.slice(0, n) + '…' : str || ''; }

function _fmtDur(s) {
    if (!isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, '0')}`;
}

function _extractDownloadUrl(text) {
    if (!text) return null;
    const m = text.match(/\[file:(\d+):/);
    return m ? `/api/files/download/${m[1]}` : null;
}

function _guessMimeFromName(name) {
    if (!name) return null;
    const ext = name.split('.').pop().toLowerCase();
    return {
        jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
        gif: 'image/gif',  webp: 'image/webp',
        mp4: 'video/mp4',  webm: 'audio/webm',
        mp3: 'audio/mpeg', ogg: 'audio/ogg',  wav: 'audio/wav',
        m4a: 'audio/mp4',
    }[ext] || null;
}

function _guessMimeFromText(text) {
    if (!text) return null;
    const m = text.match(/\[file:\d+:(.+?)\]/);
    if (!m) return null;
    return _guessMimeFromName(m[1]);
}