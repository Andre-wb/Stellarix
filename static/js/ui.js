// static/js/ui.js
// ============================================================================
// Модуль управления интерфейсом: переключение между экранами,
// открытие комнаты, отображение профиля.
// ============================================================================

import { $, api, esc } from './utils.js';
import { renderRoomsList } from './rooms.js';
import { connectWS, saveDraft, loadDraft } from './chat/chat.js';
import { cleanupUnreadDivider } from './chat/messages.js';
import { connectSignal } from './webrtc.js';
import { clearUnread } from './notifications.js';
import { getAccounts } from './auth.js';

/**
 * Показывает приветственный экран (выбор комнаты).
 * Скрывает чат, сбрасывает currentRoom, перерисовывает список комнат.
 */
export function showWelcome() {
    const welcome    = $('welcome-screen');
    const chat       = $('chat-screen');
    const navWelcome = $('nav-welcome');
    if (welcome) { welcome.classList.add('active');    welcome.style.display = 'flex'; }
    if (chat)    { chat.classList.remove('active');    chat.style.display = 'none'; }
    if (navWelcome) navWelcome.classList.add('active');
    window.AppState.currentRoom = null;

    // На мобильном: показываем sidebar (список чатов), скрываем main
    document.body.classList.remove('mobile-chat-open');

    renderRoomsList();
}

/**
 * Показывает экран чата.
 * Скрывает приветственный экран, активирует соответствующую кнопку навигации.
 */
export function showChatScreen() {
    const welcome = $('welcome-screen');
    const chat    = $('chat-screen');
    const navWelcome = $('nav-welcome');
    if (welcome) { welcome.style.display = 'none'; welcome.classList.remove('active'); }
    if (chat)    { chat.style.display = 'flex';    chat.classList.add('active'); }
    if (navWelcome) navWelcome.classList.remove('active');

    // На мобильном: показываем main (чат), скрываем sidebar
    document.body.classList.add('mobile-chat-open');

    // Ensure chats tab is active so sidebar is visible
    if (typeof window.switchBottomTab === 'function') {
        window.switchBottomTab('chats');
    }
}

/**
 * Форматирует время последнего входа пользователя для DM.
 * @param {string|null} isoDate - дата в формате ISO
 * @returns {string} - человекочитаемый текст
 */
function _formatLastSeen(isoDate) {
    if (!isoDate) return t('time.longAgo');
    const diff = (Date.now() - new Date(isoDate)) / 1000;
    if (diff < 60) return t('time.justNow');
    if (diff < 3600) return `${Math.floor(diff / 60)} ${t('time.minAgo')}`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} ${t('time.hAgo')}`;
    return new Date(isoDate).toLocaleDateString('ru');
}

/**
 * Открывает комнату с заданным ID.
 * Устанавливает currentRoom, закрывает предыдущее WebSocket-соединение,
 * очищает сообщения, подключает новые WebSocket (чат и сигнализация).
 * @param {number} id - ID комнаты
 */
export function openRoom(id) {
    const S = window.AppState;
    const room = S.rooms.find(r => r.id === id);
    if (!room) return;

    // Save draft of current room before switching
    const input = document.getElementById('msg-input');
    if (S.currentRoom && input) {
        saveDraft(S.currentRoom.id, input.value);
    }

    S.currentRoom = room;
    clearUnread(id);

    // Remove "not in contacts" banner from previous room
    const oldBanner = document.getElementById('not-contact-banner');
    if (oldBanner) oldBanner.remove();

    if (S.ws) {
        S.ws.onclose = null;
        if (S.ws._ping) clearInterval(S.ws._ping);
        S.ws.close();
        S.ws = null;
    }
    cleanupUnreadDivider();
    showChatScreen();
    const msgContainer = $('messages-container');
    if (msgContainer) msgContainer.innerHTML = '';

    // Восстанавливаем область ввода по умолчанию
    const inputArea = document.getElementById('input-area');
    if (inputArea) inputArea.style.display = '';

    const roomNameEl = $('chat-room-name');
    const roomMetaEl = $('chat-room-meta');

    if (room.is_channel) {
        if (roomNameEl) roomNameEl.textContent = room.name;
        if (roomMetaEl) {
            roomMetaEl.textContent = `${room.subscriber_count || room.member_count || 0} ${t('rooms.subscribers')}`;
            roomMetaEl.style.color = '';
        }
        document.querySelectorAll('.header-btn-members').forEach(b => b.style.display = '');
        // Скрываем область ввода для не-админов
        if (inputArea && !room.is_owner && !room.is_admin) {
            inputArea.style.display = 'none';
        }
        // Copy protection enforcement
        const msgContainer = document.getElementById('messages-container');
        if (msgContainer) {
            if (room.copy_protection) {
                msgContainer.style.userSelect = 'none';
                msgContainer.style.webkitUserSelect = 'none';
                msgContainer.oncontextmenu = (e) => { e.preventDefault(); return false; };
            } else {
                msgContainer.style.userSelect = '';
                msgContainer.style.webkitUserSelect = '';
                msgContainer.oncontextmenu = null;
            }
        }
    // Show / hide Mini App button
    const miniAppBtn = document.getElementById('mini-app-btn');
    if (miniAppBtn) {
        miniAppBtn.style.display = (room.is_dm && room.dm_user?.is_bot) ? 'flex' : 'none';
    }
    // Close any open mini-app panel when switching rooms
    window.closeMiniApp?.();

    } else if (room.is_dm && room.dm_user) {
        if (roomNameEl) roomNameEl.textContent = room.dm_user.display_name || room.dm_user.username || t('chat.dm');
        const dmU = room.dm_user;
        const dmPresence = dmU.presence || 'online';
        const isOnline = dmU.is_online || room.online_count > 1;
        // Build meta text: presence-aware + rich status
        let metaParts = [];
        if (dmPresence === 'dnd') {
            metaParts.push(t('status.dnd'));
        } else if (dmPresence === 'away') {
            metaParts.push(t('status.away'));
        } else if (dmPresence === 'invisible') {
            metaParts.push(t('status.offline'));
        } else if (isOnline) {
            metaParts.push(t('time.online'));
        } else {
            metaParts.push(_formatLastSeen(dmU.last_seen));
        }
        // Append rich status text if available
        const richStatus = ((dmU.status_emoji || '') + (dmU.status_emoji && dmU.custom_status ? ' ' : '') + (dmU.custom_status || '')).trim();
        if (richStatus) metaParts.push(richStatus);

        if (roomMetaEl) {
            roomMetaEl.textContent = metaParts.join(' \u00B7 ');
            if (dmPresence === 'dnd') {
                roomMetaEl.style.color = 'var(--red)';
            } else if (dmPresence === 'away') {
                roomMetaEl.style.color = 'var(--yellow)';
            } else if (isOnline && dmPresence === 'online') {
                roomMetaEl.style.color = 'var(--green)';
            } else {
                roomMetaEl.style.color = '';
            }
        }
        // Скрываем кнопку "Участники" и "Опрос" для DM
        document.querySelectorAll('.header-btn-members').forEach(b => b.style.display = 'none');
        const pollBtn = document.getElementById('poll-btn');
        if (pollBtn) pollBtn.style.display = 'none';
        // Fingerprint shield
        if (typeof window.updateShieldForRoom === 'function') {
            window.updateShieldForRoom(room, dmU);
        }
    } else {
        if (roomNameEl) roomNameEl.textContent = room.name;
        if (roomMetaEl) {
            roomMetaEl.textContent = t('rooms.membersOnline', {n: room.member_count, m: room.online_count});
            roomMetaEl.style.color = '';
        }
        document.querySelectorAll('.header-btn-members').forEach(b => b.style.display = '');
        const pollBtn = document.getElementById('poll-btn');
        if (pollBtn) pollBtn.style.display = '';
    }

    // Hide fingerprint shield for non-DM rooms
    if (!room.is_dm) {
        const fpShield = document.getElementById('chat-fp-shield');
        if (fpShield) fpShield.style.display = 'none';
    }

    // Show/hide channel-specific menu items
    const channelItems = document.getElementById('header-channel-items');
    if (channelItems) {
        channelItems.style.display = (room.is_channel && (room.is_owner || room.is_admin || room.my_role === 'owner' || room.my_role === 'admin')) ? '' : 'none';
    }

    // Check for active stream in channel
    if (room.is_channel && typeof window.checkStreamStatus === 'function') {
        window.checkStreamStatus(id).then(resp => {
            const banner = document.getElementById('stream-live-banner');
            if (banner) {
                if (resp.is_live) {
                    const titleEl = banner.querySelector('.stream-live-banner-title');
                    if (titleEl) titleEl.textContent = resp.stream?.title || 'Live';
                    const countEl = banner.querySelector('.stream-live-banner-count');
                    if (countEl) countEl.textContent = resp.stream?.viewer_count || 0;
                    banner.style.display = '';
                    banner.onclick = () => { if (window.joinStream) window.joinStream(id); };
                } else {
                    banner.style.display = 'none';
                }
            }
        }).catch(() => {});
    }

    // Apply per-room theme if set, otherwise restore global theme
    if (typeof window.applyRoomThemeToChat === 'function') {
        let theme = null;
        try {
            theme = room.theme_json ? (typeof room.theme_json === 'string' ? JSON.parse(room.theme_json) : room.theme_json) : null;
        } catch(e) {}
        window.applyRoomThemeToChat(theme);
    }

    renderRoomsList();
    connectWS(id);
    // ✅ Федеративные комнаты всегда сигналят через виртуальный ID = -1
    const signalId = room.is_federated ? -1 : id;
    connectSignal(signalId);

    // Отмечаем комнату как прочитанную на сервере
    api('POST', `/api/rooms/${id}/read`).catch(() => {});

    // Сохраняем последнюю открытую комнату для авто-открытия
    localStorage.setItem('vortex_last_room', String(id));

    // Restore draft for the new room
    const msgInput = document.getElementById('msg-input');
    if (msgInput) {
        const draft = loadDraft(id);
        msgInput.value = draft;
        msgInput.style.height = 'auto';
        if (draft) {
            msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + 'px';
        }
    }
}

/**
 * Открывает модальное окно профиля текущего пользователя.
 * Заполняет данные из AppState.user и рендерит список аккаунтов.
 */
export function showProfileModal() {
    const S = window.AppState;
    if (!S.user) return;
    const profPhone = $('prof-phone');
    const profUsername = $('prof-username');
    const profCreated = $('prof-created');
    if (profPhone) profPhone.textContent = S.user.phone || '';
    if (profUsername) profUsername.textContent = '@' + S.user.username;
    const created = S.user.created_at ? new Date(S.user.created_at).toLocaleDateString('ru') : t('time.justNow');
    if (profCreated) profCreated.textContent = created;

    // Update rich status display in profile modal
    const profDot = document.getElementById('prof-status-dot');
    const profStatusText = document.getElementById('prof-status-text');
    const presence = S.user.presence || 'online';
    if (profDot) profDot.className = 'status-dot ' + presence;
    if (profStatusText) {
        const emoji = S.user.status_emoji || '';
        const text  = S.user.custom_status || '';
        if (emoji || text) {
            profStatusText.textContent = (emoji ? emoji + ' ' : '') + text;
        } else {
            const presenceLabels = { online: t('status.online'), away: t('status.away'), dnd: t('status.dnd'), invisible: t('status.invisible') };
            profStatusText.textContent = presenceLabels[presence] || t('status.setStatus');
        }
    }

    // Рендерим список аккаунтов
    _renderAccountsList();

    // Load moderation status
    _loadModerationStatus();

    window.openModal('profile-modal');
}

/**
 * Рендерит список сохранённых аккаунтов в профильной модалке.
 */
function _renderAccountsList() {
    const container = $('accounts-list');
    if (!container) return;

    const accounts = getAccounts();
    const currentId = window.AppState.user?.user_id;

    let html = '';
    for (const acc of accounts) {
        const isCurrent = acc.user_id === currentId;
        const avatarContent = acc.avatar_url
            ? `<img src="${esc(acc.avatar_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`
            : esc(acc.avatar_emoji || '\u{1F464}');

        html += `<div class="ma-account-row${isCurrent ? ' ma-active' : ''}"
                      ${isCurrent ? '' : `onclick="switchAccount(${acc.user_id})"`}
                      title="${isCurrent ? t('settings.currentAccount') : t('settings.switchAccount')}">
            <div class="ma-account-avatar">${avatarContent}</div>
            <div class="ma-account-info">
                <div class="ma-account-name">${esc(acc.display_name)}</div>
                <div class="ma-account-uname">@${esc(acc.username)}</div>
            </div>
            ${isCurrent
                ? '<div class="ma-account-badge"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg></div>'
                : `<button class="ma-account-remove" onclick="event.stopPropagation();removeAccount(${acc.user_id});showProfileModal();" title="${t('settings.removeAccount')}">&times;</button>`
            }
        </div>`;
    }

    // Кнопка добавления аккаунта (если < 4)
    if (accounts.length < 4) {
        html += `<div class="ma-account-row ma-add-row" onclick="addNewAccount()">
            <div class="ma-account-avatar ma-add-icon">+</div>
            <div class="ma-account-info">
                <div class="ma-account-name">${t('auth.register')}</div>
            </div>
        </div>`;
    }

    container.innerHTML = html;
}

/**
 * Loads moderation status (strikes, mute) and displays it in the profile modal.
 */
async function _loadModerationStatus() {
    const modEl = document.getElementById('prof-moderation');
    const titleEl = document.getElementById('prof-mod-title');
    const detailEl = document.getElementById('prof-mod-detail');
    if (!modEl || !titleEl || !detailEl) return;

    try {
        const data = await window.api('GET', '/api/moderation/strikes');
        if (data.strike_count > 0 || data.is_muted) {
            modEl.style.display = 'block';
            titleEl.textContent = '\u26A0\uFE0F ' + t('chat.warnings') + ': ' + data.strike_count + '/5';
            let detail = '';
            if (data.is_muted && data.muted_remaining) {
                detail = t('chat.mutedRemaining') + ': ' + data.muted_remaining;
            } else if (data.strike_count > 0) {
                detail = t('chat.nextViolationWarning');
            }
            detailEl.textContent = detail;
        } else {
            modEl.style.display = 'none';
        }
    } catch (e) {
        modEl.style.display = 'none';
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Rich Status Editor
// ══════════════════════════════════════════════════════════════════════════════

let _statusEditorEmoji = null;
let _statusEditorPresence = 'online';

/**
 * Update the sidebar user badge to reflect rich status.
 */
export function updateSidebarStatus() {
    const S = window.AppState;
    if (!S.user) return;

    const presence = S.user.presence || 'online';
    const dot = document.getElementById('sb-status-dot');
    if (dot) {
        dot.className = 'status-dot ' + presence;
    }

    const stEl = document.getElementById('sb-status-text');
    if (stEl) {
        const emoji = S.user.status_emoji || '';
        const text  = S.user.custom_status || '';
        if (emoji || text) {
            stEl.textContent = (emoji ? emoji + ' ' : '') + text;
            stEl.style.display = '';
        } else {
            stEl.textContent = '';
            stEl.style.display = 'none';
        }
    }
}

/**
 * Open the status editor modal, pre-filled with current status.
 */
export function openStatusEditor() {
    const S = window.AppState;
    _statusEditorEmoji = S.user?.status_emoji || null;
    _statusEditorPresence = S.user?.presence || 'online';

    const emojiBtn = document.getElementById('status-emoji-pick');
    if (emojiBtn) emojiBtn.textContent = _statusEditorEmoji || '\u{1F60A}';

    const textInput = document.getElementById('status-text-input');
    if (textInput) {
        textInput.value = S.user?.custom_status || '';
        _updateStatusCharCount();
    }

    // Highlight current presence
    document.querySelectorAll('#presence-presets .presence-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.presence === _statusEditorPresence);
    });

    // Highlight current emoji preset
    document.querySelectorAll('#status-emoji-presets button').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.trim() === (_statusEditorEmoji || ''));
    });

    document.getElementById('status-editor-modal').classList.add('open');
    const textInput2 = document.getElementById('status-text-input');
    if (textInput2) setTimeout(() => textInput2.focus(), 50);
}

function _updateStatusCharCount() {
    const input = document.getElementById('status-text-input');
    const counter = document.getElementById('status-char-num');
    if (input && counter) counter.textContent = input.value.length;
}
window._updateStatusCharCount = _updateStatusCharCount;

function _pickStatusEmoji(emoji) {
    _statusEditorEmoji = emoji;
    const btn = document.getElementById('status-emoji-pick');
    if (btn) btn.textContent = emoji;
    document.querySelectorAll('#status-emoji-presets button').forEach(b => {
        b.classList.toggle('active', b.textContent.trim() === emoji);
    });
}
window._pickStatusEmoji = _pickStatusEmoji;

function _cycleStatusEmoji() {
    const presets = ['\u{1F60A}', '\u{1F3E0}', '\u{1F3AF}', '\u{1F3A7}', '\u{1F4BB}', '\u{1F4F1}', '\u{1F355}', '\u{2708}\u{FE0F}', '\u{1F319}', '\u{1F534}', '\u{1F912}', '\u{1F4DA}'];
    const idx = presets.indexOf(_statusEditorEmoji);
    _pickStatusEmoji(presets[(idx + 1) % presets.length]);
}
window._cycleStatusEmoji = _cycleStatusEmoji;

function _pickPresence(p) {
    _statusEditorPresence = p;
    document.querySelectorAll('#presence-presets .presence-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.presence === p);
    });
}
window._pickPresence = _pickPresence;

async function _saveRichStatus() {
    const textInput = document.getElementById('status-text-input');
    const customText = textInput ? textInput.value.trim().slice(0, 70) : '';
    try {
        const data = await api('PUT', '/api/authentication/status', {
            custom_status: customText || null,
            status_emoji:  _statusEditorEmoji || null,
            presence:      _statusEditorPresence,
        });
        if (data.ok && window.AppState.user) {
            window.AppState.user.custom_status = data.custom_status;
            window.AppState.user.status_emoji  = data.status_emoji;
            window.AppState.user.presence      = data.presence;
            updateSidebarStatus();
        }
    } catch (e) {
        console.warn('saveRichStatus:', e.message);
    }
    document.getElementById('status-editor-modal').classList.remove('open');
}
window._saveRichStatus = _saveRichStatus;

async function _clearRichStatus() {
    try {
        const data = await api('PUT', '/api/authentication/status', {
            custom_status: null,
            status_emoji:  null,
            presence:      'online',
        });
        if (data.ok && window.AppState.user) {
            window.AppState.user.custom_status = null;
            window.AppState.user.status_emoji  = null;
            window.AppState.user.presence      = 'online';
            updateSidebarStatus();
        }
    } catch (e) {
        console.warn('clearRichStatus:', e.message);
    }
    document.getElementById('status-editor-modal').classList.remove('open');
}
window._clearRichStatus = _clearRichStatus;

/**
 * Helper: generate HTML for an avatar with a status dot overlay.
 * @param {object} obj - must have avatar_url/avatar_emoji + optional presence
 * @param {string} [cls='avatar'] - CSS class for the avatar div
 * @returns {string} HTML string
 */
export function avatarWithStatus(obj, cls) {
    cls = cls || 'avatar';
    const presence = obj.presence || 'online';
    let inner;
    if (obj.avatar_url) {
        inner = `<div class="${cls}"><img src="${esc(obj.avatar_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;"></div>`;
    } else {
        inner = `<div class="${cls}">${esc(obj.avatar_emoji || '\u{1F464}')}</div>`;
    }
    return `<div class="avatar-status-wrap">${inner}<div class="status-dot ${esc(presence)}"></div></div>`;
}

// При ресайзе на десктоп — убираем мобильный класс
window.addEventListener('resize', function() {
    if (window.innerWidth > 640) {
        document.body.classList.remove('mobile-chat-open');
    }
});

