// static/js/chat/banners.js — "Not in contacts" banner + DM theme proposal banner

import { appendSystemMessage } from './messages.js';
import { renderRoomsList } from '../rooms.js';
import { showWelcome } from '../ui.js';

// =============================================================================
// "Not in contacts" banner for DMs
// =============================================================================

export function _showNotContactBanner(otherUserId) {
    let banner = document.getElementById('not-contact-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'not-contact-banner';
        banner.className = 'not-contact-banner';
        banner.innerHTML = `
            <div class="not-contact-text">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
                ${t('chat.notInContacts')}
            </div>
            <div class="not-contact-actions">
                <button class="btn btn-primary btn-sm" onclick="_acceptNotContact(${otherUserId})">${t('chat.addToContacts')}</button>
                <button class="btn btn-danger btn-sm" onclick="_blockUser(${otherUserId})">${t('chat.blockUser')}</button>
            </div>
        `;
        const messagesContainer = document.getElementById('messages-container');
        messagesContainer.parentNode.insertBefore(banner, messagesContainer);
    }
}

export function _hideNotContactBanner() {
    const banner = document.getElementById('not-contact-banner');
    if (banner) banner.remove();
}

window._acceptNotContact = async function(userId) {
    try {
        const { api } = await import('../utils.js');
        await api('POST', '/api/contacts', { user_id: userId });
        _hideNotContactBanner();
        appendSystemMessage(t('chat.userAddedToContacts'));
    } catch(e) { alert(e.message); }
};

window._blockUser = async function(userId) {
    if (!confirm(t('chat.blockConfirm'))) return;
    try {
        const { api } = await import('../utils.js');
        await api('POST', `/api/users/block/${userId}`);
        _hideNotContactBanner();
        appendSystemMessage(t('chat.userBlocked'));
        const S = window.AppState;
        if (S.currentRoom) {
            S.rooms = S.rooms.filter(r => r.id !== S.currentRoom.id);
            renderRoomsList();
            showWelcome();
        }
    } catch(e) { alert(e.message); }
};

// =============================================================================
// Bot DM tag — show BOT badge instead of "not in contacts"
// =============================================================================

export function _showBotTag() {
    _hideNotContactBanner();
    let tag = document.getElementById('bot-dm-tag');
    if (tag) return;
    tag = document.createElement('div');
    tag.id = 'bot-dm-tag';
    tag.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;background:var(--bg3);border-bottom:1px solid var(--border);font-size:12px;color:var(--text2);';

    var icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    icon.setAttribute('width', '16');
    icon.setAttribute('height', '16');
    icon.setAttribute('fill', 'var(--accent)');
    icon.setAttribute('viewBox', '0 0 24 24');
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z');
    icon.appendChild(path);

    var badge = document.createElement('span');
    badge.style.cssText = 'font-weight:700;color:var(--accent);';
    badge.textContent = 'BOT';

    var label = document.createElement('span');
    label.textContent = t('bots.botConversation');

    tag.appendChild(icon);
    tag.appendChild(badge);
    tag.appendChild(label);

    var mc = document.getElementById('messages-container');
    if (mc) mc.parentNode.insertBefore(tag, mc);
}

export function _hideBotTag() {
    var el = document.getElementById('bot-dm-tag');
    if (el) el.remove();
}

// =============================================================================
// DM Theme proposal banner
// =============================================================================

export function _showThemeProposalBanner(msg) {
    // Remove existing banner
    const old = document.getElementById('theme-proposal-banner');
    if (old) old.remove();

    const banner = document.createElement('div');
    banner.id = 'theme-proposal-banner';
    banner.className = 'not-contact-banner';
    banner.style.background = 'var(--bg3)';
    const name = msg.proposed_by_name || 'User';
    const wallpaper = msg.theme?.wallpaper || '';
    const accent = msg.theme?.accent || '';
    let desc = t('chat.themeProposal').replace('{name}', name);
    if (wallpaper) desc += ': ' + wallpaper;
    if (accent) desc += ' (' + accent + ')';

    banner.innerHTML = `
        <div class="not-contact-text" style="flex:1;">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M12 22C6.49 22 2 17.51 2 12S6.49 2 12 2s10 4.04 10 9c0 3.31-2.69 6-6 6h-1.77c-.28 0-.5.22-.5.5 0 .12.05.23.13.33.41.47.64 1.06.64 1.67A2.5 2.5 0 0112 22zm0-18c-4.41 0-8 3.59-8 8s3.59 8 8 8c.28 0 .5-.22.5-.5a.54.54 0 00-.14-.35c-.41-.46-.63-1.05-.63-1.65a2.5 2.5 0 012.5-2.5H16c2.21 0 4-1.79 4-4 0-3.86-3.59-7-8-7z"/></svg>
            ${desc}
        </div>
        <div class="not-contact-actions">
            <button class="btn btn-primary btn-sm" onclick="_acceptThemeProposal(${msg.room_id})">${t('chat.acceptTheme')}</button>
            <button class="btn btn-danger btn-sm" onclick="_rejectThemeProposal(${msg.room_id})">${t('chat.rejectTheme')}</button>
        </div>
    `;
    const messagesContainer = document.getElementById('messages-container');
    if (messagesContainer) {
        messagesContainer.parentNode.insertBefore(banner, messagesContainer);
    }
}

window._acceptThemeProposal = async function(roomId) {
    try {
        const { api } = await import('../utils.js');
        await api('POST', `/api/rooms/${roomId}/theme/accept`);
        const banner = document.getElementById('theme-proposal-banner');
        if (banner) banner.remove();
    } catch(e) { alert(e.message); }
};

window._rejectThemeProposal = async function(roomId) {
    try {
        const { api } = await import('../utils.js');
        await api('POST', `/api/rooms/${roomId}/theme/reject`);
        const banner = document.getElementById('theme-proposal-banner');
        if (banner) banner.remove();
    } catch(e) { alert(e.message); }
};
