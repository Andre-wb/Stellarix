// static/js/chat/send.js — reply/edit state, sendMessage, sendStickerDirect, handleKey, handleTyping

import { scrollToBottom } from '../utils.js';
import { getRoomKey, ratchetEncrypt } from '../crypto.js';
import { appendSystemMessage } from './messages.js';
import { extractMentions } from './messages.js';
import { sendWithAck } from './ack.js';
import { _checkMentionAutocomplete, _closeMentionDropdown, _insertMention } from './mention.js';
import { saveDraft, _clearDraft } from './draft.js';
import { isScheduleMode, getScheduleDatetime, resetScheduleMode } from './features.js';

// =============================================================================
// State
// =============================================================================

let _replyTo      = null;
let _editingId    = null;
let _typingActive = false;
let _draftTimer   = null;

// =============================================================================
// Reply / Edit
// =============================================================================

window.setReplyTo = (msg, quoteText) => {
    _replyTo   = msg;
    _replyTo._quoteText = quoteText || null;
    _editingId = null;
    const bar  = document.getElementById('reply-bar');
    const name = document.getElementById('reply-bar-name');
    const text = document.getElementById('reply-bar-text');
    if (bar) {
        bar.classList.add('visible');
        if (name) name.textContent = msg.display_name || msg.sender || '?';
        if (text) text.textContent = _truncate(quoteText || msg.text || msg.file_name || t('chat.file'), 60);
    }
    document.getElementById('msg-input')?.focus();
};

window.cancelReply = () => {
    _replyTo   = null;
    _editingId = null;
    const bar = document.getElementById('reply-bar');
    if (bar) { bar.classList.remove('visible'); delete bar.dataset.mode; }
    const input = document.getElementById('msg-input');
    if (input) { input.placeholder = t('chat.messagePlaceholder'); input.value = ''; }
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
        if (nameEl) nameEl.textContent = t('chat.editing');
        if (textEl) textEl.textContent = _truncate(msg.text || '', 60);
    }
    const input = document.getElementById('msg-input');
    if (input) { input.value = msg.text || ''; input.focus(); }
};

window.deleteMessage = (msgId) => {
    const S = window.AppState;
    if (!msgId || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    try {
        S.ws.send(JSON.stringify({ action: 'delete_message', msg_id: msgId }));
    } catch (e) { console.warn('deleteMessage ws.send failed:', e.message); }
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
            appendSystemMessage(t('chat.noRoomKeySend'));
            return;
        }
        const ciphertext = await ratchetEncrypt(text, S.currentRoom.id, S.user.id, roomKey);
        S.ws?.send(JSON.stringify({ action: 'edit_message', msg_id: _editingId, ciphertext }));
        _editingId = null;
        const bar = document.getElementById('reply-bar');
        if (bar) { bar.classList.remove('visible'); delete bar.dataset.mode; }
    } else {
        if (!roomKey) {
            appendSystemMessage(t('chat.keyNotReceivedWait'));
            return;
        }
        const ciphertext = await ratchetEncrypt(text, S.currentRoom.id, S.user.id, roomKey);

        // Отложенное сообщение (Feature 2)
        if (isScheduleMode()) {
            const payload = { action: 'schedule_message', ciphertext, scheduled_at: getScheduleDatetime() };
            if (_replyTo?.msg_id) payload.reply_to_id = _replyTo.msg_id;
            S.ws?.send(JSON.stringify(payload));
            _replyTo = null;
            resetScheduleMode();
            const bar4 = document.getElementById('reply-bar');
            if (bar4) { bar4.classList.remove('visible'); delete bar4.dataset.mode; }
            input.value = '';
            input.style.height = 'auto';
            return;
        }

        // Самоуничтожающееся сообщение
        if (window.isTimedMode?.()) {
            const payload = { action: 'timed_message', ciphertext, ttl_seconds: window.getTimedTtl?.() };
            sendWithAck(payload).catch(err => {
                console.error('[ACK] timed msg не доставлено:', err.message);
            });
            _replyTo = null;
            const bar3 = document.getElementById('reply-bar');
            if (bar3) { bar3.classList.remove('visible'); delete bar3.dataset.mode; }
            input.value = '';
            input.style.height = 'auto';
            return;
        }

        const payload    = { action: 'message', ciphertext, client_ts: new Date().toISOString() };
        if (_replyTo?.msg_id) {
            payload.reply_to_id = _replyTo.msg_id;
            if (_replyTo._quoteText) payload.reply_quote = _replyTo._quoteText;
        }

        // Pass @mentioned usernames so server can flag notifications
        const mentions = extractMentions(text);
        if (mentions.length) payload.mentioned_usernames = mentions;

        // If text starts with '/', include plaintext so server can forward to bots
        if (text.startsWith('/')) payload.plaintext_command = text;

        sendWithAck(payload).catch(err => {
            console.error('[ACK] не доставлено:', err.message);
        });

        _replyTo = null;
        _closeMentionDropdown();
        const bar2 = document.getElementById('reply-bar');
        if (bar2) { bar2.classList.remove('visible'); delete bar2.dataset.mode; }
    }

    input.value = '';
    input.style.height = 'auto';
    _clearDraft(S.currentRoom?.id);
}

/**
 * Отправляет стикер напрямую через WS, минуя input.
 */
export async function sendStickerDirect(text) {
    const S = window.AppState;
    if (!S?.currentRoom || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    const roomKey = getRoomKey(S.currentRoom.id);
    if (!roomKey) {
        appendSystemMessage(t('chat.keyNotReceived') + '.');
        return;
    }
    const ciphertext = await ratchetEncrypt(text, S.currentRoom.id, S.user.id, roomKey);
    sendWithAck({ action: 'message', ciphertext }).catch(err => {
        console.error('[ACK] sticker not delivered:', err.message);
    });
}

export function handleKey(e) {
    // Ctrl+E / Cmd+E — toggle emoji picker
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        window._toggleEmojiPicker?.();
        return;
    }

    // Handle mention dropdown navigation
    const dropdown = document.getElementById('mention-dropdown');
    if (dropdown && dropdown.children.length > 0) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const items = dropdown.querySelectorAll('.mention-item');
            const active = dropdown.querySelector('.mention-item.active');
            let idx = Array.from(items).indexOf(active);
            if (e.key === 'ArrowDown') idx = Math.min(idx + 1, items.length - 1);
            else idx = Math.max(idx - 1, 0);
            items.forEach(i => i.classList.remove('active'));
            items[idx]?.classList.add('active');
            items[idx]?.scrollIntoView({ block: 'nearest' });
            return;
        }
        if (e.key === 'Tab' || (e.key === 'Enter' && dropdown.querySelector('.mention-item.active'))) {
            e.preventDefault();
            const active = dropdown.querySelector('.mention-item.active');
            if (active) _insertMention(active.dataset.username);
            return;
        }
        if (e.key === 'Escape') {
            _closeMentionDropdown();
            return;
        }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

export function handleTyping() {
    const input = document.getElementById('msg-input');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';

    // Slash command menu
    _checkSlashMenu(input);

    const S = window.AppState;
    if (!_typingActive && S.ws?.readyState === WebSocket.OPEN) {
        _typingActive = true;
        try { S.ws.send(JSON.stringify({ action: 'typing', is_typing: true })); } catch {}
        if (window.bmpMarkActivity) window.bmpMarkActivity('typing');
    }
    clearTimeout(S.typingTimeout);
    S.typingTimeout = setTimeout(() => {
        _typingActive = false;
        try { S.ws?.send(JSON.stringify({ action: 'typing', is_typing: false })); } catch {}
    }, 2000);

    // Debounced draft save (500ms)
    clearTimeout(_draftTimer);
    _draftTimer = setTimeout(() => {
        if (S.currentRoom) saveDraft(S.currentRoom.id, input.value);
    }, 500);

    // @mention autocomplete
    _checkMentionAutocomplete(input);
}

// ═══════════════════════════════════════════════════════════════════════════
// Slash command menu — shows bot commands when typing "/"
// ═══════════════════════════════════════════════════════════════════════════

let _slashMenuEl = null;

function _checkSlashMenu(input) {
    const text = input.value;

    // Show menu when text starts with "/" and is short
    if (text.startsWith('/') && text.length < 30 && !text.includes(' ')) {
        _showSlashMenu(text);
    } else {
        _closeSlashMenu();
    }
}

async function _showSlashMenu(typed) {
    const S = window.AppState;
    if (!S.currentRoom) return;

    // Get bot commands for this room
    let commands = S._roomBotCommands;
    if (!commands) {
        try {
            const { api } = await import('../utils.js');
            const data = await api('GET', '/api/rooms/' + S.currentRoom.id + '/bot-commands');
            commands = data.commands || [];
            S._roomBotCommands = commands;
        } catch { commands = []; S._roomBotCommands = []; }
    }

    if (!commands.length) { _closeSlashMenu(); return; }

    // Filter by typed prefix
    const query = typed.toLowerCase();
    const filtered = commands.filter(function(c) {
        return c.command.toLowerCase().startsWith(query);
    });

    if (!filtered.length) { _closeSlashMenu(); return; }

    if (!_slashMenuEl) {
        _slashMenuEl = document.createElement('div');
        _slashMenuEl.id = 'slash-cmd-menu';
        _slashMenuEl.className = 'slash-cmd-menu';
        var inputArea = document.getElementById('input-area');
        if (inputArea) inputArea.appendChild(_slashMenuEl);
    }

    _slashMenuEl.textContent = '';
    filtered.forEach(function(cmd) {
        var item = document.createElement('div');
        item.className = 'slash-cmd-item';

        var cmdSpan = document.createElement('span');
        cmdSpan.className = 'slash-cmd-name';
        cmdSpan.textContent = cmd.command;

        var descSpan = document.createElement('span');
        descSpan.className = 'slash-cmd-desc';
        descSpan.textContent = cmd.description || '';

        item.appendChild(cmdSpan);
        item.appendChild(descSpan);

        item.addEventListener('click', function() {
            var input = document.getElementById('msg-input');
            if (input) {
                input.value = cmd.command + ' ';
                input.focus();
            }
            _closeSlashMenu();
        });

        _slashMenuEl.appendChild(item);
    });

    _slashMenuEl.style.display = '';
}

function _closeSlashMenu() {
    if (_slashMenuEl) {
        _slashMenuEl.style.display = 'none';
    }
}

// Clear cached commands when room changes
window.addEventListener('message', function(e) {
    if (e.data === 'room-changed') {
        window.AppState._roomBotCommands = null;
    }
});

// Expose on window so features.js can call window.sendMessage() and
// window.sendStickerDirect() at runtime without a circular import.
window.sendMessage       = sendMessage;
window.sendStickerDirect = sendStickerDirect;
