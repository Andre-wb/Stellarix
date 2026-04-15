import { esc, fmtTime, fmtDate, fmtSize } from '../../utils.js';
import { getRoomKey, decryptFile } from '../../crypto.js';

/** Fetch + decrypt video with progress callback, return blob URL */
async function _fetchVideoWithProgress(url, onProgress) {
    const resp = await fetch(url, { credentials: 'include' });
    const total = parseInt(resp.headers.get('content-length') || '0', 10);
    let buf;
    if (total && resp.body) {
        const reader = resp.body.getReader();
        const chunks = [];
        let loaded = 0;
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
            loaded += value.length;
            onProgress(Math.min(99, Math.round(loaded / total * 100)));
        }
        buf = new Uint8Array(loaded);
        let off = 0;
        for (const c of chunks) { buf.set(c, off); off += c.length; }
        buf = buf.buffer;
    } else {
        onProgress(50);
        buf = await resp.arrayBuffer();
    }
    onProgress(100);
    const rk = getRoomKey(window.AppState?.currentRoom?.id);
    if (rk && buf.byteLength > 28) {
        try { buf = await decryptFile(new Uint8Array(buf).buffer, rk); } catch(_) {}
    }
    const blob = new Blob([buf], { type: 'video/mp4' });
    return URL.createObjectURL(blob);
}

import { initLiquidGlass, createReplyQuote } from '../liquid-glass.js';
import { loadEncryptedImage, loadEncryptedMedia, downloadAndDecryptFile } from '../file-upload.js';
import {
    _maybeAttachLinkPreview, _buildPreviewCard, _renderBotMarkdown,
    _renderTextWithMentions, _notifyMention, extractMentions,
    _attachSwipeReply, _resetSwipe, _avatarHtml, _translateMessage,
    _ensureContextMenuStyles, _showContextMenu, _closeContextMenu,
    _loadReminders, _saveReminders, _showReminderModal, _scheduleReminder,
    _fireReminder, _showEditHistory, _buildReplyQuote,
    _attachMobileLongPress,
} from './helpers.js';
import { _msgElements, _msgTexts } from './shared.js';
import { _buildVoiceBubble, _initVoiceBubble, _guessMimeFromName, _guessMimeFromText, _extractDownloadUrl } from './voice.js';
import { _attachSelectionLongPress } from './selection.js';
import { attachStickerClickHandler } from './stickers.js';
import { _pluralReplies } from './threads.js';
import { _attachReactionLongPress } from './reactions.js';

let _lastDate     = null;
let _lastSenderId = null;

// Document type detection for rich preview cards
const _DOC_TYPES = {
    pdf:  { label: 'PDF',  name: 'PDF Document',       color: '#ef4444' },
    doc:  { label: 'DOC',  name: 'Word Document',      color: '#2563eb' },
    docx: { label: 'DOCX', name: 'Word Document',      color: '#2563eb' },
    xls:  { label: 'XLS',  name: 'Excel Spreadsheet',  color: '#16a34a' },
    xlsx: { label: 'XLSX', name: 'Excel Spreadsheet',   color: '#16a34a' },
    ppt:  { label: 'PPT',  name: 'Presentation',       color: '#ea580c' },
    pptx: { label: 'PPTX', name: 'Presentation',       color: '#ea580c' },
    txt:  { label: 'TXT',  name: 'Text File',          color: '#6b7280' },
    rtf:  { label: 'RTF',  name: 'Rich Text',          color: '#6b7280' },
    odt:  { label: 'ODT',  name: 'OpenDocument Text',  color: '#2563eb' },
    ods:  { label: 'ODS',  name: 'OpenDocument Sheet',  color: '#16a34a' },
    odp:  { label: 'ODP',  name: 'OpenDocument Slides', color: '#ea580c' },
    csv:  { label: 'CSV',  name: 'CSV Data',           color: '#16a34a' },
    md:   { label: 'MD',   name: 'Markdown',           color: '#8b5cf6' },
    json: { label: 'JSON', name: 'JSON Data',          color: '#eab308' },
    xml:  { label: 'XML',  name: 'XML Data',           color: '#06b6d4' },
    html: { label: 'HTML', name: 'HTML Page',           color: '#ea580c' },
    zip:  { label: 'ZIP',  name: 'Archive',            color: '#78716c' },
    rar:  { label: 'RAR',  name: 'Archive',            color: '#78716c' },
    '7z': { label: '7Z',   name: 'Archive',            color: '#78716c' },
    // Code files
    css:  { label: 'CSS',  name: 'Stylesheet',         color: '#2563eb' },
    js:   { label: 'JS',   name: 'JavaScript',         color: '#eab308' },
    ts:   { label: 'TS',   name: 'TypeScript',         color: '#3178c6' },
    yaml: { label: 'YAML', name: 'YAML Config',        color: '#cb171e' },
    yml:  { label: 'YML',  name: 'YAML Config',        color: '#cb171e' },
    py:   { label: 'PY',   name: 'Python',             color: '#3572a5' },
    php:  { label: 'PHP',  name: 'PHP',                color: '#4f5d95' },
    java: { label: 'JAVA', name: 'Java',               color: '#b07219' },
    c:    { label: 'C',    name: 'C Source',            color: '#555555' },
    cpp:  { label: 'C++',  name: 'C++ Source',          color: '#f34b7d' },
    cs:   { label: 'C#',   name: 'C# Source',           color: '#178600' },
    go:   { label: 'GO',   name: 'Go Source',           color: '#00add8' },
    rs:   { label: 'RS',   name: 'Rust Source',         color: '#dea584' },
    rb:   { label: 'RB',   name: 'Ruby',               color: '#701516' },
    swift:{ label: 'SWIFT',name: 'Swift',               color: '#f05138' },
    kt:   { label: 'KT',   name: 'Kotlin',             color: '#a97bff' },
    dart: { label: 'DART', name: 'Dart',                color: '#00b4ab' },
    sh:   { label: 'SH',   name: 'Shell Script',       color: '#89e051' },
    sql:  { label: 'SQL',  name: 'SQL Query',           color: '#e38c00' },
    // Web page bundle
    vxpage:{ label: 'PAGE', name: 'Web Page',           color: '#7c3aed' },
};

function _isDocumentType(fileName) {
    if (!fileName) return false;
    const ext = fileName.split('.').pop().toLowerCase();
    return ext in _DOC_TYPES;
}

function _getDocType(fileName) {
    const ext = (fileName || '').split('.').pop().toLowerCase();
    return { ext, ..._DOC_TYPES[ext] } || { ext, label: ext.toUpperCase(), name: 'File', color: '#6b7280' };
}

export function resetMessageState() {
    _lastDate     = null;
    _lastSenderId = null;
    _msgElements.clear();
    _msgTexts.clear();
}

/**
 * Добавляет текстовое сообщение в контейнер.
 * Если сообщение имеет тип 'file'/'image'/'voice', перенаправляет в appendFileMessage.
 *
 * @param {Object} msg - объект сообщения от сервера
 */
export function appendMessage(msg) {
    _ensureContextMenuStyles();

    // Если это файл (включая изображения и голос), обрабатываем отдельно
    if (msg.msg_type === 'file' || msg.msg_type === 'image' || msg.msg_type === 'voice') {
        return appendFileMessage({
            sender_id:    msg.sender_id,
            sender:       msg.sender,
            display_name: msg.display_name,
            avatar_emoji: msg.avatar_emoji,
            avatar_url:   msg.avatar_url,
            tag:          msg.tag,
            tag_color:    msg.tag_color,
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
            text:            msg.text,
        });
    }

    const S         = window.AppState;
    const container = document.getElementById('messages-container');
    const isOwn     = msg.sender_id === S.user?.user_id;

    // Разделитель по дате
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
    group.className        = `fade-in msg-group${isOwn ? ' msg-group-own' : ''}`;
    group.dataset.msgId    = msg.msg_id || '';
    group.dataset.senderId = msg.sender_id || '';

    const room = S.currentRoom;
    const isDm = room && room.is_dm;

    // В DM не показываем имя/аватар — ты знаешь кому пишешь
    if (showAuthor && !isOwn && !isDm) {
        const author = document.createElement('div');
        author.className = 'msg-author';

        // In channels, show channel name+avatar instead of individual sender
        const isChannel = room && room.is_channel;
        const authorName = isChannel
            ? (room.name || msg.display_name || msg.sender || '?')
            : (msg.display_name || msg.sender || '?');
        const avatarObj = isChannel
            ? { avatar_url: room.avatar_url, avatar_emoji: room.avatar_emoji || '\u{1F4E2}' }
            : msg;
        const nameClick = isChannel
            ? ''
            : (msg.sender_id ? ` style="cursor:pointer;" onclick="window.openUserProfile(${msg.sender_id})"` : '');

        // Build author header using safe helpers — _avatarHtml uses esc() internally
        const signatureHtml = (isChannel && room.admin_signatures && msg.display_name)
            ? `<span class="msg-channel-signature">${esc(msg.display_name)}</span>` : '';
        const tagHtml = msg.tag
            ? `<span class="msg-tag" ${msg.tag_color ? `style="background:${esc(msg.tag_color)}22;color:${esc(msg.tag_color)};border-color:${esc(msg.tag_color)}44"` : ''}>${esc(msg.tag)}</span>`
            : '';
        author.innerHTML = `
            ${_avatarHtml(avatarObj)}
            <span class="msg-name"${nameClick}>${esc(authorName)}</span>
            ${tagHtml}
            ${msg.is_bot ? '<span class="msg-bot-badge">BOT</span>' : ''}
            <span class="msg-time">${fmtTime(msg.created_at)}</span>
            ${signatureHtml}
            ${msg.from_peer ? '<span class="msg-peer-badge">P2P</span>' : ''}`;
        group.appendChild(author);
    }

    // Check if this is a sticker or GIF — render without glass background
    const _isSticker = msg.text && msg.text.startsWith('[STICKER] ');
    const _isGif = msg.text && msg.text.startsWith('[GIF] ');
    const _isMediaMsg = _isSticker || _isGif;

    // Hide author time for media messages (time shown as overlay on media)
    if (_isMediaMsg) {
        const authorTime = group.querySelector('.msg-time');
        if (authorTime) authorTime.style.display = 'none';
    }

    const bubble = document.createElement('div');
    bubble.className = _isMediaMsg
        ? `msg-bubble msg-bubble-media${isOwn ? ' own' : ''}`
        : `msg-bubble lg${isOwn ? ' lg-own own' : ''}`;

    // Apply sender's custom reply bubble color + scattered icons
    if (!isOwn && msg.reply_color) {
        bubble.style.setProperty('--sender-reply-color', msg.reply_color);
        bubble.style.borderLeft = `3px solid ${msg.reply_color}`;
    }
    if (!isOwn && msg.reply_icon) {
        const iconLayer = document.createElement('div');
        iconLayer.className = 'msg-reply-icons';
        // Scatter 12 tiny icons across the bubble
        for (let i = 0; i < 12; i++) {
            const span = document.createElement('span');
            span.textContent = msg.reply_icon;
            span.style.cssText = `position:absolute;font-size:${8 + Math.random() * 6}px;opacity:${0.06 + Math.random() * 0.08};left:${Math.random() * 90}%;top:${Math.random() * 85}%;transform:rotate(${Math.random() * 60 - 30}deg);pointer-events:none;user-select:none;`;
            iconLayer.appendChild(span);
        }
        bubble.style.position = 'relative';
        bubble.appendChild(iconLayer);
    }

    if (!_isMediaMsg) {
        const grain = document.createElement('div');
        grain.className = 'lg-grain';
        bubble.appendChild(grain);
    }

    if (msg.reply_to_id && msg.reply_to_text) {
        bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
    }

    const textEl = document.createElement('span');
    textEl.className   = 'msg-text';

    // Sticker messages — render as animated sticker, custom image sticker, or large emoji
    if (msg.text && msg.text.startsWith('[STICKER] ')) {
        const stickerPayload = msg.text.substring(10).trim();
        // Custom image sticker: "[STICKER] img:/uploads/stickers/..."
        if (stickerPayload.startsWith('img:')) {
            const imgUrl = stickerPayload.substring(4);
            const safeUrl = esc(imgUrl);
            textEl.innerHTML = `<img src="${safeUrl}" class="custom-sticker" alt="sticker">`;
            // Attach click → pack popup (после вставки в DOM)
            requestAnimationFrame(() => attachStickerClickHandler(textEl));
        }
        // Animated sticker: "[STICKER] vortex:wave"
        else {
            const packMatch = stickerPayload.match(/^(\w+):(\w+)$/);
            if (packMatch) {
                const _animStickerMap = {
                    wave:'\u{1F44B}', heart:'\u{2764}\u{FE0F}', fire:'\u{1F525}', laugh:'\u{1F602}',
                    cry:'\u{1F62D}', thumbsup:'\u{1F44D}', party:'\u{1F389}', rocket:'\u{1F680}',
                    star:'\u{2B50}', cool:'\u{1F60E}', love:'\u{1F970}', clap:'\u{1F44F}',
                    think:'\u{1F914}', scared:'\u{1F631}', angry:'\u{1F621}', sleep:'\u{1F634}',
                    money:'\u{1F911}', ghost:'\u{1F47B}', hundred:'\u{1F4AF}', eyes:'\u{1F440}'
                };
                const sName = packMatch[2];
                const emoji = _animStickerMap[sName] || '\u{2753}';
                const animClass = _animStickerMap[sName] ? 'sticker-' + sName : '';
                textEl.innerHTML = `<span class="animated-sticker ${animClass}">${emoji}</span>`;
            } else {
                // Legacy plain-emoji sticker: "[STICKER] emoji"
                textEl.innerHTML = `<span style="font-size:64px;line-height:1;">${stickerPayload}</span>`;
            }
        }
    }
    // Feature 4: GIF messages — render as inline image
    else if (msg.text && msg.text.startsWith('[GIF] ')) {
        const gifUrl = msg.text.substring(6).trim();
        const safeUrl = esc(gifUrl);
        textEl.innerHTML = `<img src="${safeUrl}" style="max-width:250px;border-radius:8px;cursor:pointer;display:block;" onclick="window.open('${safeUrl}','_blank')" alt="GIF">`;
    }
    // Payment / invoice messages — render as invoice card
    else if (msg.text && msg.text.startsWith('[PAY] ')) {
        const payJson = msg.text.substring(6).trim();
        try {
            const pay = JSON.parse(payJson);
            const _cryptoCurrencies = ['BTC', 'ETH', 'USDT', 'TON'];
            const isCrypto = _cryptoCurrencies.includes(pay.currency);
            const cardClass = isCrypto ? 'invoice-crypto' : 'invoice-fiat';

            // Currency symbols
            const _sym = {RUB:'₽',USD:'$',EUR:'€',BTC:'₿',ETH:'Ξ',USDT:'₮',TON:'◎'};
            const sym = _sym[pay.currency] || '';

            // QR for crypto
            let qrData = '';
            if (isCrypto && pay.address) {
                if (pay.currency === 'BTC') qrData = 'bitcoin:' + pay.address + (pay.amount ? '?amount=' + pay.amount : '');
                else if (pay.currency === 'ETH') qrData = 'ethereum:' + pay.address;
                else if (pay.currency === 'TON') qrData = 'ton://transfer/' + pay.address + (pay.amount ? '?amount=' + pay.amount : '');
                else qrData = pay.address;
            }

            // Format date
            const _fmtDate = d => { try { return new Date(d).toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric'}); } catch { return d; } };

            // Truncate address
            const addr = pay.address || '';
            const addrShort = addr.length > 24 ? addr.substring(0, 12) + '···' + addr.substring(addr.length - 8) : addr;

            let h = `<div class="invoice-card ${cardClass}">`;
            // Header
            h += `<div class="invoice-header">`;
            h += `<div class="invoice-icon">${isCrypto
                ? '<svg width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg>'
                : '<svg width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>'
            }</div>`;
            h += `<div class="invoice-header-text">`;
            h += `<div class="invoice-title">${esc(pay.title || t('invoice.title'))}</div>`;
            if (pay.sender) h += `<div class="invoice-from">${t('invoice.from')} ${esc(pay.sender)}</div>`;
            h += `</div>`;
            if (pay.network) h += `<span class="invoice-network">${esc(pay.network)}</span>`;
            h += `</div>`;

            // Amount
            h += `<div class="invoice-amount-row">`;
            h += `<span class="invoice-amount">${sym ? sym + ' ' : ''}${esc(String(pay.amount))}</span>`;
            h += `<span class="invoice-currency-badge">${esc(pay.currency)}</span>`;
            h += `</div>`;

            // Info rows
            h += `<div class="invoice-details">`;
            if (pay.recipient) h += `<div class="invoice-row"><span class="invoice-label">${t('invoice.recipient')}</span><span class="invoice-value">${esc(pay.recipient)}</span></div>`;
            if (pay.due_date) h += `<div class="invoice-row"><span class="invoice-label">${t('invoice.payBefore')}</span><span class="invoice-value invoice-due">${_fmtDate(pay.due_date)}</span></div>`;
            if (pay.created) h += `<div class="invoice-row"><span class="invoice-label">${t('invoice.issued')}</span><span class="invoice-value">${_fmtDate(pay.created)}</span></div>`;
            if (pay.description) h += `<div class="invoice-row"><span class="invoice-label">${t('invoice.description')}</span><span class="invoice-value">${esc(pay.description)}</span></div>`;
            h += `</div>`;

            // Address
            h += `<div class="invoice-address-row">`;
            h += `<code class="invoice-address" title="${esc(addr)}">${esc(addrShort)}</code>`;
            h += `<button class="invoice-copy-btn" onclick="navigator.clipboard.writeText('${esc(addr).replace(/'/g, "\\'")}');this.innerHTML='<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'14\\' height=\\'14\\' fill=\\'currentColor\\' viewBox=\\'0 0 24 24\\'><path d=\\'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z\\'/></svg>';setTimeout(()=>{this.textContent=t('ctx.copy')},1500)">${t('ctx.copy')}</button>`;
            h += `</div>`;

            // QR
            if (isCrypto && qrData) {
                const qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=' + encodeURIComponent(qrData);
                h += `<div class="invoice-qr"><img src="${esc(qrUrl)}" alt="QR" width="120" height="120" loading="lazy" style="border-radius:8px;"></div>`;
            }

            // Pay button
            h += `<button class="invoice-pay-btn" onclick="this.classList.toggle('paid');this.innerHTML=this.classList.contains('paid')?'<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'14\\' height=\\'14\\' fill=\\'currentColor\\' viewBox=\\'0 0 24 24\\'><path d=\\'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z\\'/></svg> '+t('invoice.markPaid'):t('invoice.markPaid')">${t('invoice.markPaid')}</button>`;
            h += `</div>`;
            textEl.innerHTML = h;
        } catch (_e) {
            textEl.textContent = msg.text;
        }
    }
    // Feature 3: Location messages — render as clickable link with map icon
    else if (msg.text && msg.text.includes('maps.google.com/maps?q=')) {
        const lines = msg.text.split('\n');
        const mapLink = lines.find(l => l.includes('maps.google.com'));
        const label = lines.find(l => !l.includes('maps.google.com')) || '';
        const safeLink = esc(mapLink || '');
        const safeLabel = esc(label);
        textEl.innerHTML = `<div style="display:flex;flex-direction:column;gap:4px;">
            <span>${safeLabel}</span>
            <a href="${safeLink}" target="_blank" rel="noopener" style="color:var(--accent2);text-decoration:underline;font-size:12px;word-break:break-all;">${safeLink}</a>
        </div>`;
    }
    else if (msg.is_bot && msg.text && msg.text.startsWith('[MINIAPP]')) {
        // Mini App card — bot sends [MINIAPP] {"url":"...", "title":"...", "button_text":"Open"}
        try {
            const jsonStr = msg.text.substring('[MINIAPP]'.length).trim();
            const appData = JSON.parse(jsonStr);
            const appTitle = esc(appData.title || 'Mini App');
            const btnText = esc(appData.button_text || 'Open App');
            const appUrl = appData.url || '';
            const botId = msg.bot_id || 0;
            textEl.innerHTML = `<div class="miniapp-card">
                <div class="miniapp-card-title">${appTitle}</div>
                <button class="miniapp-card-btn" onclick="window.openMiniApp(${botId}, '${esc(appUrl)}', '${appTitle}')">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/><path d="M14 9l3 3-3 3"/></svg>
                    ${btnText}
                </button>
            </div>`;
        } catch (_e) {
            textEl.innerHTML = _renderBotMarkdown(msg.text);
        }
    }
    else if (msg.is_bot && msg.text) {
        // Bot messages support simple markdown: **bold**, _italic_, `code`, [text](url)
        textEl.innerHTML = _renderBotMarkdown(msg.text);
    }
    else {
        _renderTextWithMentions(textEl, msg.text || '', isOwn);
    }
    bubble.appendChild(textEl);

    // For stickers/GIF — add time pill inside the content element
    if (_isMediaMsg) {
        const mediaTime = document.createElement('div');
        mediaTime.className = 'media-time-inline';
        mediaTime.textContent = fmtTime(msg.created_at);
        textEl.appendChild(mediaTime);
    }

    // Syntax-highlight any fenced code blocks
    if (typeof hljs !== 'undefined') {
        textEl.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
    }

    // Link preview (OG meta card)
    _maybeAttachLinkPreview(msg.text, bubble);

    // Пометка «переслано»
    if (msg.forwarded_from) {
        const fwd = document.createElement('div');
        fwd.className = 'msg-forwarded';
        fwd.textContent = `${t('ctx.forwardedFrom')} ${msg.forwarded_from}`;
        bubble.insertBefore(fwd, textEl);
    }

    if (msg.is_edited) {
        const ed = document.createElement('span');
        ed.className   = 'msg-edited-mark';
        ed.textContent = ' ' + t('ctx.edited');
        ed.title = t('chat.showEditHistory') || 'Show edit history';
        ed.style.cursor = 'pointer';
        if (msg.msg_id) {
            ed.addEventListener('click', (e) => {
                e.stopPropagation();
                _showEditHistory(msg.msg_id, window.AppState?.currentRoom?.id);
            });
        }
        bubble.appendChild(ed);
    }

    // Иконка статуса доставки (для своих сообщений)
    if (isOwn) {
        const statusEl = document.createElement('span');
        statusEl.className = 'msg-status' + (msg.status === 'read' ? ' read' : '');
        const checkSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
        const dblCheckSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41L6 19l1.41-1.41L1.83 12 .41 13.41z"/></svg>';
        statusEl.innerHTML = msg.status === 'read' ? dblCheckSvg : checkSvg;
        bubble.appendChild(statusEl);
    }

    // Самоуничтожающееся сообщение — таймер
    if (msg.expires_at) {
        const timerEl = document.createElement('span');
        timerEl.className = 'msg-timer';
        const _updateTimer = () => {
            const left = Math.max(0, (new Date(msg.expires_at) - Date.now()) / 1000);
            if (left <= 0) { timerEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M18.89 5.28l1.42-1.42-1.42-1.41-1.41 1.41L16.06 2.44 14.65 3.86l.7.7A8.007 8.007 0 0011 3.05V1h-2v2.05C5.05 3.56 2 6.92 2 11c0 4.42 3.58 8 8 8 1.45 0 2.81-.39 3.99-1.07l.71.71 1.41-1.42-1.41-1.41 1.42-1.42 1.41 1.42 1.42-1.42-1.42-1.41 1.36-1.36zM10 17c-3.31 0-6-2.69-6-6s2.69-6 6-6 6 2.69 6 6-2.69 6-6 6z"/></svg>'; return; }
            const m = Math.floor(left / 60), s = Math.floor(left % 60);
            timerEl.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:2px;"><path d="M6 2v6h.01L6 8.01 10 12l-4 4 .01.01H6V22h12v-5.99h-.01L18 16l-4-4 4-3.99-.01-.01H18V2H6zm10 14.5V20H8v-3.5l4-4 4 4zm-4-5l-4-4V4h8v3.5l-4 4z"/></svg> ${m}:${String(s).padStart(2,'0')}`;
            setTimeout(_updateTimer, 1000);
        };
        _updateTimer();
        bubble.appendChild(timerEl);
    }

    bubble.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        if (e.target.closest('.lg-reply') || e.target.closest('.msg-reactions') || e.target.closest('.msg-reaction')) return;
        _showContextMenu(e, msg, isOwn);
    });

    _attachMobileLongPress(bubble, msg, isOwn);

    if (isOwn && !_isMediaMsg) {
        const timeEl = document.createElement('div');
        timeEl.style.cssText = 'font-size:10px;color:var(--text3);margin-top:3px;text-align:right;font-family:var(--mono);';
        timeEl.textContent = fmtTime(msg.created_at);
        group.appendChild(bubble);
        group.appendChild(timeEl);
    } else {
        group.appendChild(bubble);
    }

    // Контейнер реакций
    const reactionsDiv = document.createElement('div');
    reactionsDiv.className = 'msg-reactions';
    reactionsDiv.id = `reactions-${msg.msg_id || ''}`;
    group.appendChild(reactionsDiv);

    // Рендер существующих реакций (из истории)
    if (msg.reactions && msg.reactions.length) {
        const emojiMap = {};
        msg.reactions.forEach(r => {
            if (!emojiMap[r.emoji]) emojiMap[r.emoji] = {count: 0, hasOwn: false, users: []};
            emojiMap[r.emoji].count++;
            if (r.user_id === S.user?.user_id || r.user_id === S.user?.id) emojiMap[r.emoji].hasOwn = true;
            emojiMap[r.emoji].users.push({
                user_id:      r.user_id,
                display_name: r.display_name || r.username || String(r.user_id),
                created_at:   r.created_at || null,
            });
        });
        Object.entries(emojiMap).forEach(([emoji, data]) => {
            const btn = document.createElement('span');
            btn.className = `msg-reaction${data.hasOwn ? ' own' : ''}`;
            btn.dataset.emoji = emoji;
            btn.dataset.count = data.count;
            btn.dataset.users = JSON.stringify(data.users);
            btn.innerHTML = `${emoji}${data.count > 1 ? ` <span class="reaction-count">${data.count}</span>` : ''}`;
            btn.onclick = () => {
                if (S.ws?.readyState === WebSocket.OPEN) {
                    S.ws.send(JSON.stringify({action: 'react', msg_id: msg.msg_id, emoji}));
                }
            };
            _attachReactionLongPress(btn);
            reactionsDiv.appendChild(btn);
        });
    }

    // Тред badge (показывает количество ответов в треде)
    if (msg.thread_count && msg.thread_count > 0 && msg.msg_id) {
        const threadBadge = document.createElement('div');
        threadBadge.className = 'thread-badge';
        threadBadge.id = `thread-badge-${msg.msg_id}`;
        threadBadge.textContent = _pluralReplies(msg.thread_count);
        threadBadge.addEventListener('click', (e) => {
            e.stopPropagation();
            window.openThread(msg.msg_id);
        });
        group.appendChild(threadBadge);
    }

    // Channel "Leave a comment" bar (Telegram-style)
    const _chRoom = S.currentRoom;
    if (_chRoom && _chRoom.is_channel && _chRoom.discussion_enabled && msg.msg_id) {
        const commentBar = document.createElement('div');
        commentBar.className = 'channel-comment-bar';
        const commentIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        commentIcon.setAttribute('width', '16');
        commentIcon.setAttribute('height', '16');
        commentIcon.setAttribute('fill', 'currentColor');
        commentIcon.setAttribute('viewBox', '0 0 24 24');
        const commentPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        commentPath.setAttribute('d', 'M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-1H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1z');
        commentIcon.appendChild(commentPath);
        commentBar.appendChild(commentIcon);
        const commentLabel = document.createElement('span');
        const count = msg.thread_count || 0;
        commentLabel.textContent = count > 0
            ? `${_pluralReplies(count)}`
            : (window.t ? window.t('channel.leaveComment') : 'Leave a comment');
        commentBar.appendChild(commentLabel);
        commentBar.addEventListener('click', (e) => {
            e.stopPropagation();
            window.openThread(msg.msg_id);
        });
        group.appendChild(commentBar);
    }

    container.appendChild(group);
    if (msg.msg_id) _msgElements.set(msg.msg_id, group);
    if (msg.msg_id && msg.text) {
        _msgTexts.set(msg.msg_id, {
            text:   msg.text,
            sender: msg.display_name || msg.sender || '?',
        });
    }

    // Swipe-to-reply gesture (mobile)
    _attachSwipeReply(group, msg);

    // Multi-select: long-press / Shift+click
    _attachSelectionLongPress(group, msg.msg_id);
}

/**
 * Добавляет файловое сообщение (изображение, видео, аудио, документ) в контейнер.
 *
 * @param {Object} msg - объект файлового сообщения
 */
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

    // In channels, show channel name+avatar instead of individual sender
    const _room = window.AppState?.currentRoom;
    const _isCh = _room && _room.is_channel;
    const _aName = _isCh ? (_room.name || msg.display_name || msg.sender || '?') : (msg.display_name || msg.sender || '?');
    const _aObj = _isCh ? { avatar_url: _room.avatar_url, avatar_emoji: _room.avatar_emoji || '\u{1F4E2}' } : msg;
    const _sigHtml = (_isCh && _room.admin_signatures && msg.display_name)
        ? `<span class="msg-channel-signature">${esc(msg.display_name)}</span>` : '';
    const _nameClick = (!_isCh && msg.sender_id)
        ? ` style="cursor:pointer;" onclick="window.openUserProfile(${msg.sender_id})"` : '';
    const _tagHtml = msg.tag
        ? `<span class="msg-tag" ${msg.tag_color ? `style="background:${esc(msg.tag_color)}22;color:${esc(msg.tag_color)};border-color:${esc(msg.tag_color)}44"` : ''}>${esc(msg.tag)}</span>`
        : '';
    const _isDm = _room && _room.is_dm;
    const _hideAuthor = isOwn || _isDm;
    const authorHtml = _hideAuthor ? '' : `
        <div class="msg-author">
            ${_avatarHtml(_aObj)}
            <span class="msg-name"${_nameClick}>${esc(_aName)}</span>
            ${_tagHtml}
            ${msg.is_bot ? '<span class="msg-bot-badge">BOT</span>' : ''}
            <span class="msg-time">${fmtTime(msg.created_at)}</span>
            ${_sigHtml}
        </div>`;

    // Stream recording — special card with live badge and stream styling
    const isStreamRec = (msg.msg_type === 'stream_recording' || msg.file_name?.startsWith('stream_')) && isVideo && msg.download_url;

    if (isStreamRec) {
        div.innerHTML = authorHtml;
        const card = document.createElement('div');
        card.className = `msg-bubble lg stream-rec-card${isOwn ? ' lg-own own' : ''}`;

        // Header with LIVE REPLAY badge
        const header = document.createElement('div');
        header.className = 'srec-header';
        header.innerHTML = '<div class="srec-badge"><span class="srec-badge-dot"></span> STREAM REPLAY</div>';
        card.appendChild(header);

        // Video preview
        const videoWrap = document.createElement('div');
        videoWrap.className = 'srec-video-wrap';
        const posterImg = document.createElement('img');
        posterImg.className = 'srec-poster';
        posterImg.alt = '';
        posterImg.style.background = '#111';
        posterImg.style.minHeight = '140px';

        // Try saved thumbnail
        let savedThumb = null;
        try { savedThumb = sessionStorage.getItem('vortex_vthumb_' + (msg.file_name || '')); } catch(_) {}
        if (savedThumb) posterImg.src = savedThumb;

        const playOverlay = document.createElement('div');
        playOverlay.className = 'srec-play';
        playOverlay.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="white" opacity=".9"><path d="M8 5v14l11-7z"/></svg>';

        videoWrap.append(posterImg, playOverlay);

        // Load video in background
        let _cached = null;
        loadEncryptedMedia(document.createElement('video'), msg.download_url, 'video/mp4').then(blobUrl => {
            _cached = blobUrl;
            if (!savedThumb) {
                const v = document.createElement('video');
                v.src = blobUrl; v.muted = true;
                v.addEventListener('loadeddata', () => { v.currentTime = 2; });
                v.addEventListener('seeked', () => {
                    try {
                        const c = document.createElement('canvas');
                        c.width = v.videoWidth; c.height = v.videoHeight;
                        c.getContext('2d').drawImage(v, 0, 0);
                        posterImg.src = c.toDataURL('image/jpeg', 0.85);
                    } catch(_) {}
                }, { once: true });
            }
        });

        videoWrap.addEventListener('click', () => {
            if (_cached) window._openVideoViewer?.(_cached, msg.file_name);
            else window._openVideoViewer?.(msg.download_url, msg.file_name);
        });

        card.appendChild(videoWrap);

        // Info row
        const info = document.createElement('div');
        info.className = 'srec-info';
        const nameEl = document.createElement('div');
        nameEl.className = 'srec-title';
        nameEl.textContent = (window.t?.('stream.streamRecording')||'Stream Recording');
        const metaEl = document.createElement('div');
        metaEl.className = 'srec-meta';
        metaEl.textContent = `${esc(msg.file_name || '')} \u00B7 ${fmtSize(msg.file_size || 0)}`;
        info.append(nameEl, metaEl);
        card.appendChild(info);

        card.addEventListener('contextmenu', (e) => { e.preventDefault(); _showContextMenu(e, msg, isOwn); });
        _attachMobileLongPress(card, msg, isOwn);

        div.appendChild(card);
        container.appendChild(div);
        if (msg.msg_id) _msgElements.set(msg.msg_id, div);
        _lastSenderId = msg.sender_id;
        _attachSwipeReply(div, msg);
        _attachSelectionLongPress(div, msg.msg_id);
        return;
    }

    // Video note (circular video message) — file name starts with "video_" or "videonote_"
    const isVideoNote = isVideo && (msg.file_name?.startsWith('video_') || msg.file_name?.startsWith('videonote_')) && msg.download_url;

    if (isVoice && msg.download_url) {
        div.innerHTML = authorHtml;
        const vb = _buildVoiceBubble(msg, isOwn);
        div.appendChild(vb);
    } else if (isVideoNote) {
        // Circular video note — no bubble, no glass, centered
        div.innerHTML = authorHtml;

        const container = document.createElement('div');
        container.className = 'video-note-container';
        container.style.cssText = isOwn ? 'margin-left:auto;margin-right:0;' : 'margin-left:36px;margin-right:auto;';

        const videoEl = document.createElement('video');
        videoEl.preload = 'metadata';
        videoEl.playsInline = true;
        videoEl.muted = true;
        // E2E: decrypt and load
        let _vnBlobUrl = null;
        loadEncryptedMedia(videoEl, msg.download_url, 'video/webm').then(function(url) { _vnBlobUrl = url; });

        // Auto-generate thumbnail from first frame
        videoEl.addEventListener('loadeddata', function() {
            videoEl.currentTime = 0.1;
        }, { once: true });

        const overlay = document.createElement('div');
        overlay.className = 'video-note-overlay';
        overlay.innerHTML = '<svg width="32" height="32" fill="#fff" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';

        const progress = document.createElement('div');
        progress.className = 'video-note-progress';
        const progressBar = document.createElement('div');
        progressBar.className = 'video-note-progress-bar';
        progress.appendChild(progressBar);

        container.appendChild(videoEl);
        container.appendChild(overlay);
        container.appendChild(progress);

        const _fmtSec = function(s) { var m = Math.floor(s/60); return m + ':' + String(Math.floor(s%60)).padStart(2,'0'); };
        var _vnPlaying = false;

        videoEl.ontimeupdate = function() {
            if (videoEl.duration) progressBar.style.width = (videoEl.currentTime / videoEl.duration * 100) + '%';
        };
        videoEl.onended = function() {
            videoEl.currentTime = 0;
            videoEl.muted = true;
            progressBar.style.width = '0';
            container.classList.remove('playing');
            _vnPlaying = false;
        };

        // Click on container — play/pause inline (not open viewer)
        container.addEventListener('click', function(e) {
            e.stopPropagation();
            if (_vnPlaying) {
                videoEl.pause();
                container.classList.remove('playing');
                _vnPlaying = false;
            } else {
                videoEl.muted = false;
                videoEl.play();
                container.classList.add('playing');
                _vnPlaying = true;
            }
        });

        container.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            _showContextMenu(e, msg, isOwn);
        });
        _attachMobileLongPress(container, msg, isOwn);

        div.appendChild(container);
    } else if (isImage && msg.download_url) {
        // Hide author time — shown as overlay on image
        { const _at = div.querySelector('.msg-time'); if (_at) _at.style.display = 'none'; }
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble msg-bubble-media${isOwn ? ' own' : ''}`;

        if (msg.reply_to_id && msg.reply_to_text) {
            bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
        }

        const img = document.createElement('img');
        img.alt       = esc(msg.file_name || '');
        img.className = 'chat-image';
        img.loading   = 'lazy';
        img.style.opacity = '0.3';
        img.onerror   = function() { this.closest('.msg-bubble-media')?.classList.add('file-msg'); this.remove(); };
        const _imgUrl = msg.download_url;
        loadEncryptedImage(img, _imgUrl).then(() => { img.style.opacity = '1'; });
        img.onclick   = () => window.openImageViewer(img.src, msg.file_name || '');

        const timeOverlay = document.createElement('span');
        timeOverlay.className = 'media-time-overlay';
        timeOverlay.textContent = fmtTime(msg.created_at);

        bubble.appendChild(img);
        bubble.appendChild(timeOverlay);

        // Caption text below image (if present and not a decrypt placeholder)
        const _imgCaption = msg.text;
        if (_imgCaption && !_imgCaption.startsWith('[') && _imgCaption.length > 0) {
            bubble.className = `msg-bubble lg${isOwn ? ' lg-own own' : ''}`;
            bubble.style.padding = '4px';
            const captionEl = document.createElement('div');
            captionEl.className = 'msg-text';
            captionEl.style.cssText = 'padding:6px 8px 2px;font-size:14px;';
            _renderTextWithMentions(captionEl, _imgCaption, isOwn);
            bubble.appendChild(captionEl);
        }

        bubble.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            _showContextMenu(e, msg, isOwn);
        });
        _attachMobileLongPress(bubble, msg, isOwn);

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    } else if (isVideo && msg.download_url) {
        // Hide author time — shown as overlay on video
        { const _at = div.querySelector('.msg-time'); if (_at) _at.style.display = 'none'; }
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble msg-bubble-media${isOwn ? ' own' : ''}`;

        if (msg.reply_to_id && msg.reply_to_text) {
            bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
        }

        const videoWrap = document.createElement('div');
        videoWrap.style.cssText = 'position:relative;max-width:320px;border-radius:8px;overflow:hidden;cursor:pointer;background:#000;';

        // Poster image — show thumbnail immediately, load video in background
        const posterImg = document.createElement('img');
        posterImg.style.cssText = 'width:100%;max-height:240px;display:block;object-fit:cover;';
        posterImg.alt = '';

        // Try saved thumbnail first
        let savedThumb = null;
        try { savedThumb = sessionStorage.getItem('vortex_vthumb_' + (msg.file_name || '')); } catch(_) {}
        if (savedThumb) {
            posterImg.src = savedThumb;
        } else {
            posterImg.style.background = '#111';
            posterImg.style.minHeight = '120px';
        }

        // Play button overlay
        const playBtn = document.createElement('div');
        playBtn.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.3);transition:opacity .15s;';
        playBtn.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="white" opacity="0.9"><path d="M8 5v14l11-7z"/></svg>';

        videoWrap.append(posterImg, playBtn);

        // Load video in background for caching & thumbnail generation
        let _cachedBlobUrl = null;
        const bgVideo = document.createElement('video');
        bgVideo.preload = 'metadata';
        bgVideo.muted = true;
        bgVideo.playsInline = true;
        loadEncryptedMedia(bgVideo, msg.download_url, 'video/mp4').then(blobUrl => {
            _cachedBlobUrl = blobUrl;
            if (!savedThumb && !posterImg.src) {
                // Only generate thumbnail if no poster exists yet
                bgVideo.addEventListener('seeked', () => {
                    try {
                        if (posterImg.src && !posterImg.src.endsWith('#')) return; // already has poster
                        const c = document.createElement('canvas');
                        c.width = bgVideo.videoWidth;
                        c.height = bgVideo.videoHeight;
                        c.getContext('2d').drawImage(bgVideo, 0, 0, c.width, c.height);
                        posterImg.src = c.toDataURL('image/jpeg', 0.92);
                        posterImg.style.minHeight = '';
                        posterImg.style.background = '';
                    } catch(_) {}
                }, { once: true });
                bgVideo.addEventListener('loadeddata', () => {
                    bgVideo.currentTime = Math.min(0.5, bgVideo.duration || 0);
                }, { once: true });
            }
        });

        // Prevent click right after long-press context menu
        let _longPressTriggered = false;
        bubble.addEventListener('touchstart', () => { _longPressTriggered = false; }, { passive: true });
        bubble.addEventListener('contextmenu', () => { _longPressTriggered = true; });

        videoWrap.addEventListener('click', (e) => {
            if (e.target.closest('.lg-reply')) return;
            if (_longPressTriggered) { _longPressTriggered = false; return; }
            if (_cachedBlobUrl) {
                window._openVideoViewer?.(_cachedBlobUrl, msg.file_name);
            } else {
                // Show centered percentage over thumbnail
                let loadingOverlay = videoWrap.querySelector('.video-load-overlay');
                if (loadingOverlay) return; // already loading
                loadingOverlay = document.createElement('div');
                loadingOverlay.className = 'video-load-overlay';
                const progText = document.createElement('div');
                progText.className = 'video-load-pct';
                progText.textContent = '0%';
                loadingOverlay.appendChild(progText);
                videoWrap.appendChild(loadingOverlay);
                playBtn.style.display = 'none';

                _fetchVideoWithProgress(msg.download_url, (pct) => {
                    progText.textContent = pct + '%';
                }).then(blobUrl => {
                    _cachedBlobUrl = blobUrl;
                    loadingOverlay.remove();
                    playBtn.style.display = '';
                    // Don't replace thumbnail — keep the original poster
                    window._openVideoViewer?.(blobUrl, msg.file_name);
                }).catch(() => {
                    loadingOverlay.remove();
                    playBtn.style.display = '';
                });
            }
        });

        const timeOverlay = document.createElement('span');
        timeOverlay.className = 'media-time-overlay';
        timeOverlay.textContent = fmtTime(msg.created_at);

        bubble.appendChild(videoWrap);
        bubble.appendChild(timeOverlay);

        // Caption text below video (if present and not a decrypt placeholder)
        const _vidCaption = msg.text;
        if (_vidCaption && !_vidCaption.startsWith('[') && _vidCaption.length > 0) {
            bubble.className = `msg-bubble lg${isOwn ? ' lg-own own' : ''}`;
            bubble.style.padding = '4px';
            const captionEl = document.createElement('div');
            captionEl.className = 'msg-text';
            captionEl.style.cssText = 'padding:6px 8px 2px;font-size:14px;';
            _renderTextWithMentions(captionEl, _vidCaption, isOwn);
            bubble.appendChild(captionEl);
        }

        bubble.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            _showContextMenu(e, msg, isOwn);
        });
        _attachMobileLongPress(bubble, msg, isOwn);

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    } else if (msg.download_url && msg.file_name && msg.file_name.endsWith('.vxpage.html')) {
        // Web Page preview card
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble file-msg lg${isOwn ? ' lg-own own' : ''}`;
        const grain = document.createElement('div');
        grain.className = 'lg-grain';
        bubble.appendChild(grain);

        const card = document.createElement('div');
        card.style.cssText = 'display:flex;align-items:center;gap:12px;padding:8px 4px;position:relative;z-index:4;cursor:pointer;';

        const iconW = document.createElement('div');
        iconW.style.cssText = 'width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0;background:#7c3aed;';
        iconW.textContent = '</>';

        const info = document.createElement('div');
        info.style.cssText = 'flex:1;min-width:0;';
        const nameEl = document.createElement('div');
        nameEl.style.cssText = 'font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
        nameEl.textContent = msg.file_name.replace('.vxpage.html', '');
        const sizeEl = document.createElement('div');
        sizeEl.style.cssText = 'font-size:11px;color:var(--text2);margin-top:2px;';
        sizeEl.textContent = fmtSize(msg.file_size || 0) + ' · Web Page';
        info.append(nameEl, sizeEl);

        const openBtn = document.createElement('button');
        openBtn.style.cssText = 'padding:6px 14px;border-radius:8px;border:none;background:var(--accent);color:#fff;font-size:12px;font-weight:600;cursor:pointer;flex-shrink:0;';
        openBtn.textContent = t('chat.open') || 'Open';
        openBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            window.openPageViewer?.(msg.download_url, msg.file_name.replace('.vxpage.html', ''));
        });

        card.append(iconW, info, openBtn);
        bubble.appendChild(card);
        bubble.addEventListener('contextmenu', (e) => { e.preventDefault(); _showContextMenu(e, msg, isOwn); });
        _attachMobileLongPress(bubble, msg, isOwn);

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    } else if (msg.download_url && _isDocumentType(msg.file_name)) {
        // Документ (PDF, DOC, TXT и т.д.) — карточка с иконкой и превью
        const docType = _getDocType(msg.file_name);
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble file-msg lg${isOwn ? ' lg-own own' : ''}`;

        const grain = document.createElement('div');
        grain.className = 'lg-grain';
        bubble.appendChild(grain);

        if (msg.reply_to_id && msg.reply_to_text) {
            bubble.appendChild(_buildReplyQuote(msg.reply_to_id, msg.reply_to_text, msg.reply_to_sender, isOwn));
        }

        const card = document.createElement('div');
        card.className = 'doc-preview-card';
        card.style.cssText = 'display:flex;align-items:center;gap:12px;padding:4px 0;position:relative;z-index:4;cursor:pointer;';

        const iconWrap = document.createElement('div');
        iconWrap.className = 'doc-icon-wrap';
        iconWrap.style.cssText = `width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0;background:${docType.color};`;
        iconWrap.textContent = docType.label;

        const info = document.createElement('div');
        info.style.cssText = 'flex:1;min-width:0;';
        const nameEl = document.createElement('div');
        nameEl.style.cssText = 'font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
        nameEl.textContent = msg.file_name || 'Document';
        const sizeEl = document.createElement('div');
        sizeEl.style.cssText = 'font-size:11px;color:var(--text2);margin-top:2px;';
        sizeEl.textContent = fmtSize(msg.file_size || 0) + ' · ' + docType.name;

        info.append(nameEl, sizeEl);
        card.append(iconWrap, info);

        // Кнопка скачивания
        const dlBtn = document.createElement('a');
        dlBtn.href = '#';
        dlBtn.className = 'file-download';
        dlBtn.dataset.downloadUrl = msg.download_url;
        dlBtn.dataset.fileName = msg.file_name || '';
        dlBtn.style.cssText = 'flex-shrink:0;';
        dlBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
        card.appendChild(dlBtn);

        card.addEventListener('click', (e) => {
            if (e.target.closest('.file-download')) return;
            if (!msg.download_url) {
                console.warn('[Render] No download_url for file:', msg.file_name, msg);
                if (window.showToast) window.showToast('File not available — re-upload required', 'warning');
                return;
            }
            const viewer = window.openDocViewer || window._openDocViewer;
            if (viewer) {
                viewer(msg.download_url, msg.file_name, docType.ext);
            } else {
                // Fallback: open in new tab
                window.open(msg.download_url, '_blank');
            }
        });

        bubble.appendChild(card);

        // Caption for documents
        if (msg.text && !msg.text.startsWith('[')) {
            const captionEl = document.createElement('div');
            captionEl.className = 'msg-text';
            captionEl.style.cssText = 'padding:6px 8px 2px;font-size:14px;position:relative;z-index:4;word-break:break-word;white-space:pre-wrap;';
            _renderTextWithMentions(captionEl, msg.text, isOwn);
            bubble.appendChild(captionEl);
        }

        bubble.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            _showContextMenu(e, msg, isOwn);
        });
        _attachMobileLongPress(bubble, msg, isOwn);

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    } else {
        const icon = isVideo
            ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z"/></svg>'
            : isAudio
                ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>'
                : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>';

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

        const safeName = esc(msg.file_name || t('chat.file'));
        const dlBtnHtml = msg.download_url
            ? `<a class="file-download" href="#" data-download-url="${esc(msg.download_url)}" data-file-name="${safeName}">↓ Download</a>`
            : '';

        fileContent.innerHTML = `
            <span class="file-icon">${icon}</span>
            <div class="file-info">
                <div class="file-name">${safeName}</div>
                <div class="file-size">${fmtSize(msg.file_size || 0)}</div>
            </div>
            ${dlBtnHtml}`;

        // E2E: перехватываем скачивание для расшифровки
        const dlLink = fileContent.querySelector('.file-download');
        if (dlLink) {
            dlLink.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                downloadAndDecryptFile(dlLink.dataset.downloadUrl, dlLink.dataset.fileName);
            });
        }
        bubble.appendChild(fileContent);

        // Caption for generic files
        if (msg.text && !msg.text.startsWith('[')) {
            const captionEl = document.createElement('div');
            captionEl.className = 'msg-text';
            captionEl.style.cssText = 'padding:6px 8px 2px;font-size:14px;position:relative;z-index:4;word-break:break-word;white-space:pre-wrap;';
            _renderTextWithMentions(captionEl, msg.text, isOwn);
            bubble.appendChild(captionEl);
        }

        // Click to open inline viewer for video/audio/documents
        if (msg.download_url) {
            bubble.style.cursor = 'pointer';
            bubble.addEventListener('click', (e) => {
                if (e.target.closest('.file-download') || e.target.closest('.lg-reply')) return;
                const url = msg.download_url;
                const name = msg.file_name || '';
                if (isVideo && window.openVideoViewer) {
                    window.openVideoViewer(url, name);
                } else if (isAudio && window.openAudioViewer) {
                    window.openAudioViewer(url, name);
                } else if (window.openDocViewer) {
                    window.openDocViewer(url, name, mime);
                }
            });
        }

        bubble.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (e.target.closest('.lg-reply') || e.target.closest('.file-download')) return;
            _showContextMenu(e, msg, isOwn);
        });
        _attachMobileLongPress(bubble, msg, isOwn);

        div.innerHTML = authorHtml;
        div.appendChild(bubble);
    }

    // Контейнер реакций
    const reactionsDiv = document.createElement('div');
    reactionsDiv.className = 'msg-reactions';
    reactionsDiv.id = `reactions-${msg.msg_id || ''}`;
    div.appendChild(reactionsDiv);

    if (msg.reactions && msg.reactions.length) {
        const emojiMap = {};
        msg.reactions.forEach(r => {
            if (!emojiMap[r.emoji]) emojiMap[r.emoji] = { count: 0, hasOwn: false };
            emojiMap[r.emoji].count++;
            if (r.user_id === S.user?.user_id) emojiMap[r.emoji].hasOwn = true;
        });
        for (const [emoji, data] of Object.entries(emojiMap)) {
            const btn = document.createElement('button');
            btn.className = 'msg-reaction' + (data.hasOwn ? ' own' : '');
            btn.textContent = `${emoji} ${data.count}`;
            btn.addEventListener('click', () => {
                import('./reactions.js').then(m => m._sendReaction(msg.msg_id, emoji));
            });
            reactionsDiv.appendChild(btn);
        }
    }

    _lastSenderId = msg.sender_id;
    container.appendChild(div);
    if (msg.msg_id) _msgElements.set(msg.msg_id, div);

    if (isVoice && msg.download_url) {
        _initVoiceBubble(div.querySelector('.vb-wrap'));
    }

    // Swipe-to-reply gesture (mobile)
    _attachSwipeReply(div, msg);

    // Multi-select: long-press / Shift+click
    _attachSelectionLongPress(div, msg.msg_id);
}

/**
 * Добавляет системное сообщение (например, «пользователь вошёл»).
 *
 * @param {string} text
 * @param {string} [extraClass] — дополнительный CSS-класс для стилизации
 */
export function appendSystemMessage(text, extraClass) {
    const cls = 'msg-bubble system' + (extraClass ? ' ' + extraClass : '');
    const div = document.createElement('div');
    div.innerHTML = `<div class="${cls}">${esc(text)}</div>`;
    document.getElementById('messages-container').appendChild(div);
    _lastSenderId = null;
}

/**
 * Анимирует удаление сообщения (рассыпающиеся буквы, схлопывание).
 *
 * @param {string} msgId
 */
export function deleteMessageAnim(msgId) {
    const el = _msgElements.get(msgId);
    if (!el) return;

    // Update reply quotes pointing to this deleted message
    document.querySelectorAll(`.lg-reply[data-reply-id="${msgId}"]`).forEach(q => {
        const textEl = q.querySelector('.lg-text');
        if (textEl) textEl.textContent = t('chat.messageDeleted') || 'Message deleted';
        q.style.opacity = '0.5';
        q.style.pointerEvents = 'none';
    });

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

/**
 * Обновляет текст сообщения при редактировании и подсвечивает его.
 *
 * @param {string} msgId
 * @param {string} newText
 * @param {boolean} isEdited
 */
export function updateMessageText(msgId, newText, isEdited) {
    const el = _msgElements.get(msgId);
    if (!el) return;
    const textEl = el.querySelector('.msg-text');
    if (textEl) textEl.textContent = newText;
    let edMark = el.querySelector('.msg-edited-mark');
    if (isEdited && !edMark) {
        edMark = document.createElement('span');
        edMark.className   = 'msg-edited-mark';
        edMark.textContent = ' ' + t('ctx.edited');
        edMark.title = t('chat.showEditHistory') || 'Show edit history';
        edMark.style.cursor = 'pointer';
        edMark.addEventListener('click', (e) => {
            e.stopPropagation();
            _showEditHistory(msgId, window.AppState?.currentRoom?.id);
        });
        const bubble = el.querySelector('.msg-bubble');
        if (bubble) bubble.appendChild(edMark);
    }
    const bubble = el.querySelector('.msg-bubble');
    if (bubble) {
        bubble.classList.add('msg-edited-flash');
        setTimeout(() => bubble.classList.remove('msg-edited-flash'), 700);
    }

    // Update cached text so future replies use the new version
    const cached = _msgTexts.get(msgId);
    if (cached) cached.text = newText;

    // Update all reply quotes that reference this edited message
    const container = document.getElementById('messages-container');
    if (container) {
        container.querySelectorAll('[data-reply-id="' + msgId + '"]').forEach(quote => {
            const textSpan = quote.querySelector('.lg-text');
            if (textSpan) {
                textSpan.textContent = newText.length > 80 ? newText.slice(0, 80) + '\u2026' : newText;
            }
        });
    }
}
