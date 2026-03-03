import { esc, fmtTime, fmtDate, fmtSize } from '../utils.js';

const _SVG_PLAY  = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><path d="M15.5 12L10 15.5V8.5L15.5 12Z" fill="currentColor"/></svg>`;
const _SVG_PAUSE = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><rect x="9" y="8" width="2.2" height="8" rx="1" fill="currentColor"/><rect x="12.8" y="8" width="2.2" height="8" rx="1" fill="currentColor"/></svg>`;

let _lastDate     = null;
let _lastSenderId = null;

const _msgElements = new Map();

export function resetMessageState() {
    _lastDate     = null;
    _lastSenderId = null;
    _msgElements.clear();
}

export function appendMessage(msg) {
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
            mime_type:    msg.mime_type   || _guessMimeFromName(msg.file_name)
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

    if (msg.reply_to_id && msg.reply_to_text) {
        const quote = document.createElement('div');
        quote.className = `msg-reply-quote ${isOwn ? 'own' : ''}`;
        quote.innerHTML = `
            <span class="msg-reply-sender">${esc(msg.reply_to_sender || '?')}</span>
            <span class="msg-reply-text">${esc(_truncate(msg.reply_to_text, 80))}</span>`;
        quote.onclick = () => _scrollToMsg(msg.reply_to_id);
        group.appendChild(quote);
    }

    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${isOwn ? 'own' : ''}`;

    const textEl = document.createElement('span');
    textEl.className = 'msg-text';
    textEl.textContent = msg.text || '';
    bubble.appendChild(textEl);

    if (msg.is_edited) {
        const ed = document.createElement('span');
        ed.className   = 'msg-edited-mark';
        ed.textContent = ' ред.';
        bubble.appendChild(ed);
    }

    if (isOwn) {
        const timeEl = document.createElement('div');
        timeEl.style.cssText = 'font-size:10px;color:var(--text3);margin-top:3px;text-align:right;font-family:var(--mono);';
        timeEl.textContent = fmtTime(msg.created_at);
        group.appendChild(bubble);
        group.appendChild(timeEl);
    } else {
        group.appendChild(bubble);
    }

    const actions = _buildActions(msg, isOwn);
    group.appendChild(actions);

    container.appendChild(group);
    if (msg.msg_id) _msgElements.set(msg.msg_id, group);
}

export function appendFileMessage(msg) {
    const S         = window.AppState;
    const container = document.getElementById('messages-container');
    const isOwn     = msg.sender_id === S.user?.user_id;

    const mime      = msg.mime_type || _guessMimeFromName(msg.file_name) || 'application/octet-stream';
    const isImage   = mime.startsWith('image/');
    const isVideo   = mime.startsWith('video/');
    const isAudio   = mime.startsWith('audio/');

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

    let quoteHtml = '';
    if (msg.reply_to_id && msg.reply_to_text) {
        quoteHtml = `<div class="msg-reply-quote ${isOwn ? 'own' : ''}"
            onclick="window._scrollToMsg(${msg.reply_to_id})">
            <span class="msg-reply-sender">${esc(msg.reply_to_sender || '?')}</span>
            <span class="msg-reply-text">${esc(_truncate(msg.reply_to_text, 80))}</span>
        </div>`;
    }

    if (isVoice && msg.download_url) {
        div.innerHTML = authorHtml;
        const vb = _buildVoiceBubble(msg, isOwn, quoteHtml);
        div.appendChild(vb);
    } else if (isImage && msg.download_url) {
        const safeName = esc(msg.file_name || '').replace(/'/g, "\\'");
        div.innerHTML = `
            ${authorHtml}${quoteHtml}
            <div class="msg-bubble ${isOwn ? 'own' : ''} msg-bubble-img"
                 onclick="window.openImageViewer('${msg.download_url}','${safeName}')">
                <img src="${msg.download_url}" alt="${esc(msg.file_name || '')}"
                     class="chat-image" loading="lazy"
                     onerror="this.closest('.msg-bubble-img').classList.add('file-msg');this.remove()">
                <div class="chat-image-meta">${esc(msg.file_name || '')} · ${fmtSize(msg.file_size || 0)}</div>
            </div>`;
    } else {
        const icon = isVideo ? '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" ><path d="M20 3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2M9.54 9 6.87 5h2.6l2.67 4zm5 0-2.67-4h2.6l2.67 4zM4 5h.46l2.67 4H4zm0 14v-8h16V9h-.46l-2.67-4H20v14z"></path><path d="m10 18 5-3-5-3z"></path></svg>' : isAudio ? '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" ><path d="M21 3H9c-.55 0-1 .45-1 1v9.56c-.59-.34-1.27-.56-2-.56-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V5h10v8.56c-.59-.34-1.27-.56-2-.56-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V4c0-.55-.45-1-1-1M6 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2m12 0c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2"></path></svg>' : '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" ><path d="m19.94 7.68-.03-.09a.8.8 0 0 0-.2-.29l-5-5c-.09-.09-.19-.15-.29-.2l-.09-.03a.8.8 0 0 0-.26-.05c-.02 0-.04-.01-.06-.01H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-12s-.01-.04-.01-.06c0-.09-.02-.17-.05-.26ZM6 20V4h7v4c0 .55.45 1 1 1h4v11z"/></svg>';
        div.innerHTML = `
            ${authorHtml}${quoteHtml}
            <div class="msg-bubble ${isOwn ? 'own' : ''} file-msg">
                <span class="file-icon">${icon}</span>
                <div class="file-info">
                    <div class="file-name">${esc(msg.file_name || 'файл')}</div>
                    <div class="file-size">${fmtSize(msg.file_size || 0)}</div>
                </div>
                ${msg.download_url ? `<a class="file-download" href="${msg.download_url}" download>↓ Скачать</a>` : ''}
            </div>`;
    }

    const actions = _buildActions(msg, isOwn);
    div.appendChild(actions);

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
        const p   = document.createElement('span');
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

function _buildActions(msg, isOwn) {
    const wrap = document.createElement('div');
    wrap.className = `msg-actions ${isOwn ? 'own' : ''}`;

    const replyBtn = document.createElement('button');
    replyBtn.className   = 'msg-action-btn';
    replyBtn.title       = 'Ответить';
    replyBtn.innerHTML = '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" ><path d="M9 10h6c2.21 0 4 1.79 4 4v6h2v-6c0-3.31-2.69-6-6-6H9V4L3 9l6 5z"></path></svg>';
    replyBtn.onclick     = () => window.setReplyTo(msg);
    wrap.appendChild(replyBtn);

    if (isOwn && (!msg.msg_type || msg.msg_type === 'text')) {
        const editBtn = document.createElement('button');
        editBtn.className   = 'msg-action-btn';
        editBtn.title       = 'Редактировать';
        editBtn.innerHTML = '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" > <path d="M19.67 2.61c-.81-.81-2.14-.81-2.95 0L3.38 15.95c-.13.13-.22.29-.26.46l-1.09 4.34c-.08.34.01.7.26.95.19.19.45.29.71.29.08 0 .16 0 .24-.03l4.34-1.09c.18-.04.34-.13.46-.26L21.38 7.27c.81-.81.81-2.14 0-2.95L19.66 2.6ZM6.83 19.01l-2.46.61.61-2.46 9.96-9.94 1.84 1.84zM19.98 5.86 18.2 7.64 16.36 5.8l1.78-1.78s.09-.03.12 0l1.72 1.72s.03.09 0 .12"></path></svg>';
        editBtn.onclick     = () => window.startEditMessage(msg);
        wrap.appendChild(editBtn);
    }

    if (isOwn) {
        const delBtn = document.createElement('button');
        delBtn.className   = 'msg-action-btn danger';
        delBtn.title       = 'Удалить';
        delBtn.innerHTML = '<svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" > <path d="M17 6V4c0-1.1-.9-2-2-2H9c-1.1 0-2 .9-2 2v2H2v2h2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8h2V6zM9 4h6v2H9zM6 20V8h12v12z"></path><path d="M9 10h2v8H9zm4 0h2v8h-2z"></path></svg>';
        delBtn.onclick     = () => window.deleteMessage(msg.msg_id);
        wrap.appendChild(delBtn);
    }

    return wrap;
}

function _scrollToMsg(msgId) {
    const el = _msgElements.get(msgId);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('msg-highlight');
    setTimeout(() => el.classList.remove('msg-highlight'), 1500);
}
window._scrollToMsg = _scrollToMsg;

function _truncate(str, n) { return str?.length > n ? str.slice(0, n) + '…' : str || ''; }

function _ensureVoiceStyles() {
    if (document.getElementById('vb-style')) return;
    const s = document.createElement('style');
    s.id = 'vb-style';
    s.textContent = `
    .vb-wrap {
        display:flex; flex-direction:column; gap:6px;
        padding:10px 14px; border-radius:16px;
        max-width:300px; min-width:230px; width:fit-content;
        position:relative; isolation:isolate; cursor:default;
        background:rgba(148,158,178,0.08);
        backdrop-filter:blur(22px) saturate(165%) brightness(1.07);
        -webkit-backdrop-filter:blur(22px) saturate(165%) brightness(1.07);
        border:1px solid rgba(255,255,255,0.12);
        box-shadow:inset 0 1px 0 rgba(255,255,255,0.18),
                   inset 0 -1px 0 rgba(0,0,0,0.10),
                   0 4px 22px rgba(0,0,0,0.22);
    }
    .vb-wrap::before {
        content:''; position:absolute; inset:0; border-radius:inherit;
        background:linear-gradient(135deg,rgba(255,255,255,0.11) 0%,rgba(255,255,255,0.02) 50%,transparent 100%);
        pointer-events:none; z-index:0;
    }
    .vb-wrap.own {
        margin-left:auto;
        background:rgba(88,50,168,0.12);
        border-color:rgba(180,145,255,0.18);
        box-shadow:inset 0 1px 0 rgba(210,180,255,0.18),
                   inset 0 -1px 0 rgba(0,0,0,0.12),
                   0 4px 22px rgba(0,0,0,0.20);
    }
    .vb-wrap > * { position:relative; z-index:1; }
    .vb-row { display:flex; align-items:center; gap:12px; }
    .vb-play {
        width:40px; height:40px; border-radius:50%; border:none; flex-shrink:0;
        display:flex; align-items:center; justify-content:center;
        background:rgba(255,255,255,0.14); color:#fff; cursor:pointer;
        box-shadow:0 2px 8px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.22);
        transition:transform .12s;
    }
    .vb-play:hover  { transform:scale(1.08); }
    .vb-play:active { transform:scale(.94); }
    .vb-play.played { background:rgba(180,180,195,0.18); color:rgba(255,255,255,0.45); }
    .own .vb-play   { background:rgba(195,160,255,0.20); }
    .vb-right { flex:1; display:flex; flex-direction:column; gap:5px; min-width:0; }
    .vb-bars  { display:flex; align-items:center; gap:2px; height:32px; cursor:pointer; }
    .vb-bar   { flex:1; border-radius:2px; min-width:2px;
                background:rgba(200,215,240,0.22); transition:background .1s; }
    .vb-bar.played { background:rgba(200,215,240,0.72); }
    .vb-bar.done   { background:rgba(175,180,195,0.20); }
    .own .vb-bar        { background:rgba(195,168,255,0.22); }
    .own .vb-bar.played { background:rgba(210,190,255,0.72); }
    .own .vb-bar.done   { background:rgba(175,170,195,0.20); }
    .vb-time { font-size:11px; font-family:var(--mono,monospace);
               color:rgba(255,255,255,0.38); align-self:flex-end; }
    `;
    document.head.appendChild(s);
}

function _normPeaks(peaks, N) {
    if (!peaks?.length) {
        return Array.from({length:N}, (_,i) => 0.2 + (((i * 7 + 3) % 17) / 17) * 0.65);
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

function _buildVoiceBubble(msg, isOwn, quoteHtml) {
    _ensureVoiceStyles();

    let peaks = null;
    if (msg.file_name) {
        try { peaks = JSON.parse(sessionStorage.getItem('vp:' + msg.file_name) || 'null'); } catch {}
    }

    const BARS      = 40;
    const normPeaks = _normPeaks(peaks, BARS);

    const wrap = document.createElement('div');
    wrap.className   = `vb-wrap${isOwn ? ' own' : ''}`;
    wrap.dataset.src = msg.download_url;

    if (quoteHtml) {
        const qd = document.createElement('div');
        qd.innerHTML = quoteHtml;
        const qEl = qd.firstElementChild;
        if (qEl) wrap.appendChild(qEl);
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
                // Останавливаем другие плееры
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
        jpg:'image/jpeg', jpeg:'image/jpeg', png:'image/png',
        gif:'image/gif',  webp:'image/webp',
        mp4:'video/mp4',  webm:'audio/webm',
        mp3:'audio/mpeg', ogg:'audio/ogg',  wav:'audio/wav',
        m4a:'audio/mp4',
    }[ext] || null;
}

function _guessMimeFromText(text) {
    if (!text) return null;
    const m = text.match(/\[file:\d+:(.+?)\]/);
    if (!m) return null;
    return _guessMimeFromName(m[1]);
}