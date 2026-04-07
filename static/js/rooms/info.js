// static/js/rooms/info.js — room info panel, global search, add peer, joinAndOpenChannel

import { $, api, esc, openModal, closeModal, showAlert } from '../utils.js';
import { t } from '../i18n.js';
import { showWelcome } from '../ui.js';
import { renderRoomsList, loadMyRooms } from './core.js';

// ══════════════════════════════════════════════════════════════════════════════
// Панель информации / настроек комнаты
// ══════════════════════════════════════════════════════════════════════════════

export async function openRoomInfo() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    // Don't open for DMs — DMs show user profile instead
    if (S.currentRoom.is_dm) return;

    // Federated rooms have limited info
    if (S.currentRoom.is_federated) return;

    let room;
    try {
        room = await api('GET', `/api/rooms/${S.currentRoom.id}`);
    } catch {
        room = S.currentRoom;
    }

    // Update local state with fresh data
    const keep = ['is_dm', 'dm_user', 'is_federated', 'peer_ip', 'has_key', 'is_muted', 'unread_count', 'is_owner', 'is_admin'];
    keep.forEach(k => { if (S.currentRoom[k] !== undefined && room[k] === undefined) room[k] = S.currentRoom[k]; });
    S.currentRoom = {...S.currentRoom, ...room};
    S.rooms = S.rooms.map(r => r.id === room.id ? {...r, ...room} : r);

    const isAdmin = room.my_role === 'owner' || room.my_role === 'admin';
    const isOwner = room.my_role === 'owner';

    // Avatar
    const avatarEl = $('room-info-avatar');
    const avatarWrap = $('room-info-avatar-wrap');
    if (avatarEl) {
        if (room.avatar_url) {
            avatarEl.innerHTML = `<img src="${esc(room.avatar_url)}">`;
        } else {
            avatarEl.innerHTML = '';
            avatarEl.textContent = room.avatar_emoji || '\u{1F4AC}';
        }
    }

    // Make avatar clickable for admins
    if (avatarWrap) {
        avatarWrap.className = 'room-info-avatar-wrap' + (isAdmin ? ' editable' : '');
        avatarWrap.onclick = isAdmin ? () => $('room-avatar-input').click() : null;
    }

    // Avatar upload handler
    const _avatarInput = $('room-avatar-input');
    if (_avatarInput) _avatarInput.onchange = async function() {
        if (!this.files[0]) return;
        const fd = new FormData();
        fd.append('file', this.files[0]);
        try {
            const res = await fetch(`/api/rooms/${room.id}/avatar`, {
                method: 'POST',
                body: fd,
                credentials: 'same-origin',
            });
            if (!res.ok) throw new Error('Upload failed');
            const data = await res.json();
            if (data.avatar_url) {
                if (avatarEl) avatarEl.innerHTML = `<img src="${esc(data.avatar_url)}">`;
                S.currentRoom.avatar_url = data.avatar_url;
                S.rooms = S.rooms.map(r => r.id === room.id ? {...r, avatar_url: data.avatar_url} : r);
                renderRoomsList();
            }
        } catch (e) {
            alert(t('rooms.uploadError') + ': ' + e.message);
        }
        this.value = '';
    };

    // Name, description, meta
    const _name = $('room-info-name'); if (_name) _name.textContent = room.name;
    const _desc = $('room-info-desc'); if (_desc) _desc.textContent = room.description || '';
    const createdDate = room.created_at ? new Date(room.created_at).toLocaleDateString('ru') : '';
    const _meta = $('room-info-meta'); if (_meta) _meta.textContent = `${room.member_count} ${t('rooms.members')} \u00b7 ${room.online_count} ${t('rooms.online')} \u00b7 ${createdDate}`;

    // Invite code + channel-specific UI adjustments
    const _invite = $('room-info-invite'); if (_invite) _invite.textContent = room.invite_code || '';
    const _inviteSection = $('rss-invite-section');
    const _membersBtn = $('rss-members-btn');
    const _leaveBtn = $('room-info-leave-btn');
    if (room.is_channel) {
        // Для каналов: скрыть invite-код, изменить заголовок, кнопку
        if (_inviteSection) _inviteSection.style.display = 'none';
        if (_membersBtn) _membersBtn.textContent = t('channel.subscribers') || 'Подписчики';
        if (_leaveBtn) _leaveBtn.textContent = t('channel.unsubscribe') || 'Отписаться';
        const topTitle = $('rss-topbar-title');
        if (topTitle) topTitle.textContent = t('channel.settings') || 'Настройки канала';
        const _metaEl = $('room-info-meta');
        if (_metaEl) _metaEl.textContent = `${room.member_count} ${t('channel.subscribers') || 'подписчиков'} · ${createdDate}`;
    } else {
        if (_inviteSection) _inviteSection.style.display = '';
        if (_membersBtn) _membersBtn.textContent = t('chat.members') || 'Участники';
        if (_leaveBtn) _leaveBtn.textContent = t('room.leaveShort') || 'Покинуть';
        const topTitle = $('rss-topbar-title');
        if (topTitle) topTitle.textContent = t('room.settings') || 'Настройки комнаты';
    }

    // Settings section (admin/owner only, never for DM)
    const settingsEl = $('room-info-settings');
    if (settingsEl) {
        if (isAdmin && !room.is_dm) {
            settingsEl.style.display = '';
            const _en = $('room-info-edit-name'); if (_en) _en.value = room.name || '';
            const _ed = $('room-info-edit-desc'); if (_ed) _ed.value = room.description || '';
            const _ee = $('room-info-edit-emoji'); if (_ee) _ee.value = room.avatar_emoji || '\u{1F4AC}';
            const _pr = $('room-info-private'); if (_pr) _pr.checked = !!room.is_private;
            const _ad = $('room-info-autodelete'); if (_ad) _ad.value = String(room.auto_delete_seconds || 0);

            // Show/hide channel-specific vs group-specific sections
            const channelSettings = $('rss-channel-settings');
            const groupSettings = $('rss-group-settings');

            if (room.is_channel) {
                if (channelSettings) channelSettings.style.display = '';
                if (groupSettings) groupSettings.style.display = 'none';

                // Update section title
                const secTitle = $('rss-settings-title');
                if (secTitle) secTitle.textContent = t('channel.settings') || 'Настройки канала';

                // Channel type (public/private)
                const pubToggle = $('channel-public-toggle');
                if (pubToggle) pubToggle.checked = !room.is_private;

                // Join approval
                const jaEl = $('channel-join-approval');
                if (jaEl) jaEl.checked = !!room.join_approval;

                // Discussion chat toggle
                const discEl = $('channel-discussion-enabled');
                if (discEl) discEl.checked = !!room.discussion_enabled;

                // Reactions
                const rtEl = $('channel-reactions-type');
                if (rtEl) rtEl.value = room.reactions_type || 'all';
                window._onReactionsTypeChange();
                const riEl = $('channel-reactions-input');
                if (riEl) riEl.value = room.allowed_reactions || '';

                // Admin signatures
                const asEl = $('channel-admin-signatures');
                if (asEl) asEl.checked = !!room.admin_signatures;

                // Silent default
                const sdEl = $('channel-silent-default');
                if (sdEl) sdEl.checked = !!room.silent_default;

                // Copy protection
                const cpEl = $('channel-copy-protection');
                if (cpEl) cpEl.checked = !!room.copy_protection;

                // Hashtags
                const htEl = $('channel-hashtags-enabled');
                if (htEl) htEl.checked = room.hashtags_enabled !== false;

                // Load authors
                _loadChannelAuthors(room.id);
            } else {
                if (channelSettings) channelSettings.style.display = 'none';
                if (groupSettings) groupSettings.style.display = '';

                // Group-specific settings
                const _as = $('room-info-antispam'); if (_as) _as.checked = room.antispam_enabled !== false;
                const _sm = $('room-info-slowmode'); if (_sm) _sm.value = String(room.slow_mode_seconds || 0);

                // Populate antispam settings
                let asCfg = {};
                try { asCfg = JSON.parse(room.antispam_config || '{}'); } catch(e) {}
                const _at = $('antispam-threshold'); if (_at) _at.value = String(asCfg.threshold || 15);
                const _aa = $('antispam-action'); if (_aa) _aa.value = asCfg.action || 'mute';
                const _ar = $('antispam-repeat'); if (_ar) _ar.checked = asCfg.block_repeats !== false;
                const _al = $('antispam-links'); if (_al) _al.checked = asCfg.block_links !== false;
                const asSettings = $('antispam-settings');
                if (asSettings && _as) asSettings.style.display = _as.checked ? '' : 'none';
            }

            // Delete button — owner only
            const _ds = $('room-info-delete-section'); if (_ds) _ds.style.display = isOwner ? '' : 'none';

            // Autoposting section — channels only
            const autopostEl = $('channel-autopost-section');
            if (autopostEl) {
                if (room.is_channel) {
                    autopostEl.style.display = '';
                    window._channelAutopostRoomId = room.id;
                    if (window._channelLoadFeeds) window._channelLoadFeeds(room.id);
                } else {
                    autopostEl.style.display = 'none';
                }
            }
        } else {
            settingsEl.style.display = 'none';
        }
    }

    // Update header three-dot menu: show channel items
    const channelItems = document.getElementById('header-channel-items');
    if (channelItems) {
        channelItems.style.display = (room.is_channel && isAdmin) ? '' : 'none';
    }
    const discStatus = document.getElementById('header-discussion-status');
    if (discStatus && room.is_channel) {
        discStatus.style.display = room.discussion_enabled ? '' : 'none';
        discStatus.textContent = room.discussion_enabled ? 'ON' : '';
    }

    // Открываем как полноэкранный вид внутри #main (вместо модала)
    if (typeof window.openRoomSettingsScreen === 'function') {
        window.openRoomSettingsScreen();
    } else {
        openModal('room-info-modal');
    }
}

window._roomInfoCopyInvite = function() {
    const code = $('room-info-invite').textContent;
    if (code) {
        navigator.clipboard.writeText(code).then(() => {
            $('room-info-invite').style.color = 'var(--green)';
            setTimeout(() => $('room-info-invite').style.color = '', 1000);
        });
    }
};

window._roomInfoSave = async function() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    const body = {
        name:                $('room-info-edit-name').value.trim(),
        description:         $('room-info-edit-desc').value.trim(),
        avatar_emoji:        $('room-info-edit-emoji').value.trim() || '\u{1F4AC}',
        is_private:          $('room-info-private').checked,
        auto_delete_seconds: parseInt($('room-info-autodelete').value, 10) || 0,
    };

    if (S.currentRoom.is_channel) {
        // Channel type: public toggle inverts is_private
        const pubToggle = $('channel-public-toggle');
        if (pubToggle) body.is_private = !pubToggle.checked;

        // Channel-specific settings
        const discEl = $('channel-discussion-enabled');
        if (discEl) body.discussion_enabled = discEl.checked;

        const jaEl = $('channel-join-approval');
        if (jaEl) body.join_approval = jaEl.checked;

        const rtEl = $('channel-reactions-type');
        if (rtEl) body.reactions_type = rtEl.value;

        const riEl = $('channel-reactions-input');
        if (riEl) body.allowed_reactions = riEl.value.trim();

        const asEl = $('channel-admin-signatures');
        if (asEl) body.admin_signatures = asEl.checked;

        const sdEl = $('channel-silent-default');
        if (sdEl) body.silent_default = sdEl.checked;

        const cpEl = $('channel-copy-protection');
        if (cpEl) body.copy_protection = cpEl.checked;

        const htEl = $('channel-hashtags-enabled');
        if (htEl) body.hashtags_enabled = htEl.checked;
    } else {
        // Group-specific settings
        const antispamConfig = JSON.stringify({
            threshold:     parseInt($('antispam-threshold')?.value, 10) || 15,
            action:        $('antispam-action')?.value || 'mute',
            block_repeats: $('antispam-repeat')?.checked,
            block_links:   $('antispam-links')?.checked,
        });
        body.antispam_enabled = $('room-info-antispam')?.checked;
        body.antispam_config = antispamConfig;
        body.slow_mode_seconds = parseInt($('room-info-slowmode')?.value, 10) || 0;
    }

    try {
        const updated = await api('PUT', `/api/rooms/${S.currentRoom.id}`, body);
        // Update local state
        const keep2 = ['is_dm', 'dm_user', 'is_federated', 'peer_ip', 'has_key', 'is_muted', 'unread_count', 'is_owner', 'is_admin', 'my_role'];
        keep2.forEach(k => { if (S.currentRoom[k] !== undefined && updated[k] === undefined) updated[k] = S.currentRoom[k]; });
        S.currentRoom = {...S.currentRoom, ...updated};
        S.rooms = S.rooms.map(r => r.id === updated.id ? {...r, ...updated} : r);

        // Update header
        $('chat-room-name').textContent = updated.name;
        const mc2 = updated.member_count ?? updated.subscriber_count ?? 0;
        $('chat-room-meta').textContent = `${mc2} ${t('rooms.members')} \u00b7 ${updated.online_count} ${t('rooms.online')}`;

        // Update modal display
        $('room-info-name').textContent = updated.name;
        $('room-info-desc').textContent = updated.description || '';
        if (!updated.avatar_url) {
            $('room-info-avatar').textContent = updated.avatar_emoji || '\u{1F4AC}';
            $('room-info-avatar').innerHTML = '';
            $('room-info-avatar').textContent = updated.avatar_emoji || '\u{1F4AC}';
        }

        renderRoomsList();
        if (typeof window.closeRoomSettingsScreen === 'function') window.closeRoomSettingsScreen();
        else closeModal('room-info-modal');
    } catch (e) {
        alert(t('rooms.error') + ': ' + (e.message || t('rooms.saveFailed')));
    }
};

window._roomInfoDelete = async function() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    if (!confirm(t('rooms.deleteConfirm'))) return;

    try {
        await api('DELETE', `/api/rooms/${S.currentRoom.id}`);
        S.rooms = S.rooms.filter(r => r.id !== S.currentRoom.id);
        S.currentRoom = null;
        if (typeof window.closeRoomSettingsScreen === 'function') window.closeRoomSettingsScreen();
        else closeModal('room-info-modal');
        renderRoomsList();
        showWelcome();
    } catch (e) {
        alert(t('rooms.error') + ': ' + (e.message || t('rooms.deleteFailed')));
    }
};

window._onAntispamToggle = function() {
    const enabled = $('room-info-antispam').checked;
    const settings = $('antispam-settings');
    if (settings) settings.style.display = enabled ? '' : 'none';
};

window.openRoomInfo = openRoomInfo;

// ══════════════════════════════════════════════════════════════════════════════
// Channel management: Authors, Streaming, Discussion
// ══════════════════════════════════════════════════════════════════════════════

async function _loadChannelAuthors(roomId) {
    const list = $('channel-authors-list');
    if (!list) return;
    list.replaceChildren();
    try {
        const data = await api('GET', `/api/rooms/${roomId}/members`);
        const authors = (data.members || []).filter(m => m.role === 'admin' || m.role === 'owner');
        if (!authors.length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:12px;padding:8px 0;';
            empty.textContent = t('channel.noAuthors');
            list.appendChild(empty);
            return;
        }
        authors.forEach(m => {
            const row = document.createElement('div');
            row.className = 'channel-author-row';

            const avatar = document.createElement('div');
            avatar.className = 'channel-author-avatar';
            if (m.avatar_url) {
                const img = document.createElement('img');
                img.src = m.avatar_url;
                img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:50%;';
                avatar.appendChild(img);
            } else {
                avatar.textContent = m.avatar_emoji || '\u{1F464}';
            }
            row.appendChild(avatar);

            const info = document.createElement('div');
            info.className = 'channel-author-info';
            const nameEl = document.createElement('div');
            nameEl.className = 'channel-author-name';
            nameEl.textContent = m.display_name || m.username;
            info.appendChild(nameEl);
            const roleEl = document.createElement('div');
            roleEl.className = 'channel-author-role';
            roleEl.textContent = m.role === 'owner' ? t('channel.owner') : t('channel.author');
            info.appendChild(roleEl);
            row.appendChild(info);

            // Remove button (only for non-owner)
            if (m.role !== 'owner') {
                const removeBtn = document.createElement('button');
                removeBtn.className = 'btn btn-danger btn-sm';
                removeBtn.textContent = '\u00D7';
                removeBtn.style.cssText = 'width:28px;height:28px;padding:0;font-size:16px;';
                removeBtn.onclick = async () => {
                    try {
                        await api('PUT', `/api/rooms/${roomId}/members/${m.user_id}/role`, { role: 'member' });
                        _loadChannelAuthors(roomId);
                    } catch (e) {
                        alert(e.message);
                    }
                };
                row.appendChild(removeBtn);
            }

            list.appendChild(row);
        });
    } catch (e) {
        console.warn('Failed to load authors:', e);
    }
}

window._showAddAuthorModal = async function() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const modal = $('add-author-modal');
    if (!modal) return;
    modal.style.display = '';
    const list = $('add-author-members-list');
    if (!list) return;
    list.replaceChildren();

    try {
        const data = await api('GET', `/api/rooms/${S.currentRoom.id}/members`);
        const regular = (data.members || []).filter(m => m.role === 'member');
        if (!regular.length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:12px;padding:8px 0;';
            empty.textContent = t('channel.noMembersToAdd');
            list.appendChild(empty);
            return;
        }
        regular.forEach(m => {
            const row = document.createElement('div');
            row.className = 'channel-author-row';

            const avatar = document.createElement('div');
            avatar.className = 'channel-author-avatar';
            avatar.textContent = m.avatar_emoji || '\u{1F464}';
            row.appendChild(avatar);

            const name = document.createElement('div');
            name.className = 'channel-author-name';
            name.textContent = m.display_name || m.username;
            name.style.flex = '1';
            row.appendChild(name);

            const addBtn = document.createElement('button');
            addBtn.className = 'btn btn-primary btn-sm';
            addBtn.textContent = t('channel.makeAuthor');
            addBtn.onclick = async () => {
                try {
                    await api('PUT', `/api/rooms/${S.currentRoom.id}/members/${m.user_id}/role`, { role: 'admin' });
                    _loadChannelAuthors(S.currentRoom.id);
                    modal.style.display = 'none';
                    if (window.showToast) window.showToast(t('channel.authorAdded'), 'success');
                } catch (e) {
                    alert(e.message);
                }
            };
            row.appendChild(addBtn);

            list.appendChild(row);
        });
    } catch (e) {
        console.warn('Failed to load members:', e);
    }
};

window._startChannelStream = function() {
    const S = window.AppState;
    if (!S.currentRoom || !S.currentRoom.is_channel) return;

    if (typeof window.openStreamSettings === 'function') {
        window.openStreamSettings(S.currentRoom.id);
    }
};

// Discussion toggle
window._toggleChannelDiscussion = async function() {
    const S = window.AppState;
    if (!S.currentRoom || !S.currentRoom.is_channel) return;

    const newVal = !S.currentRoom.discussion_enabled;
    try {
        await api('PUT', `/api/rooms/${S.currentRoom.id}`, { discussion_enabled: newVal });
        S.currentRoom.discussion_enabled = newVal;
        // Update UI indicator
        const discStatus = document.getElementById('header-discussion-status');
        if (discStatus) {
            discStatus.style.display = newVal ? '' : 'none';
            discStatus.textContent = newVal ? 'ON' : '';
        }
        const discCheckbox = $('channel-discussion-enabled');
        if (discCheckbox) discCheckbox.checked = newVal;
        if (window.showToast) {
            window.showToast(newVal ? t('channel.discussionEnabled') : t('channel.discussionDisabled'), 'success');
        }
    } catch (e) {
        console.error('Toggle discussion error:', e);
    }
};

// Reactions type change handler
window._onReactionsTypeChange = function() {
    const rtEl = $('channel-reactions-type');
    const picker = $('channel-reactions-picker');
    if (rtEl && picker) {
        picker.style.display = rtEl.value === 'selected' ? '' : 'none';
    }
};

// Subscribers search
window._searchChannelSubscribers = async function() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const q = $('channel-subscribers-search')?.value?.trim() || '';
    const list = $('channel-subscribers-list');
    if (!list) return;
    list.replaceChildren();
    try {
        const data = await api('GET', `/api/channels/${S.currentRoom.id}/subscribers?q=${encodeURIComponent(q)}&limit=30`);
        const subs = data.subscribers || [];
        if (!subs.length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:12px;padding:8px 0;';
            empty.textContent = t('channel.noSubscribers') || 'Нет подписчиков';
            list.appendChild(empty);
            return;
        }
        subs.forEach(s => {
            const row = document.createElement('div');
            row.className = 'channel-author-row';
            const avatar = document.createElement('div');
            avatar.className = 'channel-author-avatar';
            avatar.textContent = s.avatar_emoji || '\u{1F464}';
            row.appendChild(avatar);
            const info = document.createElement('div');
            info.className = 'channel-author-info';
            info.style.flex = '1';
            const nameEl = document.createElement('div');
            nameEl.className = 'channel-author-name';
            nameEl.textContent = s.display_name || s.username;
            info.appendChild(nameEl);
            const roleEl = document.createElement('div');
            roleEl.className = 'channel-author-role';
            roleEl.textContent = s.role === 'owner' ? (t('channel.owner') || 'Владелец') : (s.role === 'admin' ? (t('channel.author') || 'Автор') : (t('channel.subscriber') || 'Подписчик'));
            info.appendChild(roleEl);
            row.appendChild(info);
            if (s.role !== 'owner') {
                const banBtn = document.createElement('button');
                banBtn.className = 'btn btn-danger btn-sm';
                banBtn.textContent = s.is_banned ? (t('channel.unban') || 'Разбан') : (t('channel.ban') || 'Бан');
                banBtn.style.cssText = 'padding:2px 8px;font-size:11px;';
                banBtn.onclick = async () => {
                    try {
                        const endpoint = s.is_banned ? 'unban' : 'ban';
                        await api('POST', `/api/channels/${S.currentRoom.id}/subscribers/${s.user_id}/${endpoint}`);
                        window._searchChannelSubscribers();
                    } catch (e) { alert(e.message); }
                };
                row.appendChild(banBtn);
                if (s.role === 'member') {
                    const rmBtn = document.createElement('button');
                    rmBtn.className = 'btn btn-secondary btn-sm';
                    rmBtn.textContent = '\u00D7';
                    rmBtn.title = t('channel.removeSubscriber') || 'Удалить';
                    rmBtn.style.cssText = 'width:24px;height:24px;padding:0;font-size:14px;margin-left:4px;';
                    rmBtn.onclick = async () => {
                        if (!confirm(t('channel.removeConfirm') || `Удалить ${s.display_name}?`)) return;
                        try {
                            await api('DELETE', `/api/channels/${S.currentRoom.id}/subscribers/${s.user_id}`);
                            window._searchChannelSubscribers();
                        } catch (e) { alert(e.message); }
                    };
                    row.appendChild(rmBtn);
                }
            }
            list.appendChild(row);
        });
    } catch (e) {
        console.warn('Failed to load subscribers:', e);
    }
};

// Banned subscribers
window._showBannedSubscribers = async function() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const list = $('channel-banned-list');
    if (!list) return;
    list.style.display = list.style.display === 'none' ? '' : 'none';
    if (list.style.display === 'none') return;
    list.replaceChildren();
    try {
        const data = await api('GET', `/api/channels/${S.currentRoom.id}/banned`);
        const banned = data.banned || [];
        if (!banned.length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:12px;padding:8px 0;';
            empty.textContent = t('channel.noBanned') || 'Нет заблокированных';
            list.appendChild(empty);
            return;
        }
        banned.forEach(b => {
            const row = document.createElement('div');
            row.className = 'channel-author-row';
            const avatar = document.createElement('div');
            avatar.className = 'channel-author-avatar';
            avatar.textContent = b.avatar_emoji || '\u{1F464}';
            row.appendChild(avatar);
            const nameEl = document.createElement('div');
            nameEl.className = 'channel-author-name';
            nameEl.style.flex = '1';
            nameEl.textContent = b.display_name || b.username;
            row.appendChild(nameEl);
            const unbanBtn = document.createElement('button');
            unbanBtn.className = 'btn btn-secondary btn-sm';
            unbanBtn.textContent = t('channel.unban') || 'Разбан';
            unbanBtn.style.cssText = 'padding:2px 8px;font-size:11px;';
            unbanBtn.onclick = async () => {
                try {
                    await api('POST', `/api/channels/${S.currentRoom.id}/subscribers/${b.user_id}/unban`);
                    window._showBannedSubscribers();
                } catch (e) { alert(e.message); }
            };
            row.appendChild(unbanBtn);
            list.appendChild(row);
        });
    } catch (e) {
        console.warn('Failed to load banned:', e);
    }
};

// Recent actions log
window._loadRecentActions = async function() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    const list = $('channel-recent-actions');
    if (!list) return;
    list.replaceChildren();
    try {
        const data = await api('GET', `/api/channels/${S.currentRoom.id}/recent-actions`);
        const actions = data.actions || [];
        if (!actions.length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:12px;padding:8px 0;';
            empty.textContent = t('channel.noRecentActions') || 'Нет действий за 48 часов';
            list.appendChild(empty);
            return;
        }
        actions.forEach(a => {
            const row = document.createElement('div');
            row.style.cssText = 'padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;display:flex;justify-content:space-between;align-items:center;';
            const typeLabel = a.type === 'join' ? (t('channel.actionJoin') || 'Вступил')
                            : a.type === 'edit' ? (t('channel.actionEdit') || 'Редактировал пост')
                            : a.type;
            const left = document.createElement('span');
            left.textContent = `${esc(a.user)} — ${typeLabel}`;
            row.appendChild(left);
            if (a.at) {
                const right = document.createElement('span');
                right.style.cssText = 'color:var(--text3);font-size:10px;font-family:var(--mono);';
                const d = new Date(a.at);
                right.textContent = d.toLocaleString('ru', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
                row.appendChild(right);
            }
            list.appendChild(row);
        });
    } catch (e) {
        console.warn('Failed to load actions:', e);
    }
};

// ── Глобальный режим: поиск комнат по mesh-сети ──────────────────────────────

let _globalSearchTimeout = null;

export async function searchGlobalRooms(query) {
    clearTimeout(_globalSearchTimeout);
    const el = $('global-room-results');
    if (!el) return;
    if (!query.trim()) { el.innerHTML = ''; return; }

    _globalSearchTimeout = setTimeout(async () => {
        el.innerHTML = `<div style="padding:16px;color:var(--text2);">${t('rooms.searching')}</div>`;
        try {
            const data = await api('GET', `/api/global/search-rooms?q=${encodeURIComponent(query.trim())}`);
            const rooms = data.rooms || [];

            if (!rooms.length) {
                el.innerHTML = `<div style="padding:16px;color:var(--text2);">${t('rooms.nothingFound')}</div>`;
                return;
            }

            el.innerHTML = rooms.map(r => {
                const joinHandler = r.peer_ip
                    ? `window.joinPublicRoom(${r.id},'${r.invite_code}','${r.peer_ip}',${r.peer_port})`
                    : `window.joinPublicRoom(${r.id},'${r.invite_code}')`;
                const peerBadge = r.peer_ip
                    ? `<div style="font-size:10px;color:var(--text3);font-family:var(--mono);margin-top:2px;"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:2px;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg> ${esc(r.peer_name || r.peer_ip)}</div>`
                    : '';
                return `
                  <div style="padding:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;">
                    <div style="font-size:24px;">${r.is_private
                        ? '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>'
                        : '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>'}</div>
                    <div style="flex:1;">
                      <div style="font-weight:700;">${esc(r.name)}</div>
                      <div style="font-size:12px;color:var(--text2);font-family:var(--mono);">${r.member_count} ${t('rooms.members')}</div>
                      ${peerBadge}
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="${joinHandler}">${t('rooms.joinRoom')}</button>
                  </div>`;
            }).join('');
        } catch (e) {
            el.innerHTML = `<div style="padding:16px;color:var(--red);">${esc(e.message)}</div>`;
        }
    }, 500);
}

// ── Глобальный режим: добавление узла ────────────────────────────────────────

export async function addGlobalPeer() {
    const addr = $('peer-address').value.trim();
    if (!addr) return;
    try {
        const parts = addr.split(':');
        const ip   = parts[0];
        const port = parseInt(parts[1]) || 8000;
        await api('POST', '/api/global/add-peer', { ip, port });
        showAlert('add-peer-alert', t('rooms.peerAdded'), 'success');
        $('peer-address').value = '';
        closeModal('add-peer-modal');
    } catch (e) {
        showAlert('add-peer-alert', e.message);
    }
}

// ── Глобальный поиск (sidebar) ────────────────────────────────────────────────

let _globalSearchTimer = null;

export async function globalSearch(query) {
    clearTimeout(_globalSearchTimer);
    const resultsEl = document.getElementById('global-search-results');

    if (!query || query.trim().length < 2) {
        resultsEl.style.display = 'none';
        resultsEl.innerHTML = '';
        return;
    }

    _globalSearchTimer = setTimeout(async () => {
        try {
            const data = await api('GET', `/api/users/global-search?q=${encodeURIComponent(query.trim())}`);
            let html = '';

            // Users
            if (data.users && data.users.length) {
                html += `<div class="search-section-label">${t('rooms.users')}</div>`;
                data.users.forEach(u => {
                    const avatar = u.avatar_url
                        ? `<img src="${esc(u.avatar_url)}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;">`
                        : `<span style="font-size:20px;">${esc(u.avatar_emoji || '\u{1F464}')}</span>`;
                    html += `<div class="search-result-item" onclick="${u.is_self ? '' : `openDM(${u.user_id})`}" style="${u.is_self ? 'opacity:0.5;' : 'cursor:pointer;'}">
                        ${avatar}
                        <div class="room-body">
                            <div style="font-weight:700;font-size:13px;">${esc(u.display_name)}</div>
                            <div style="font-size:11px;color:var(--text3);">@${esc(u.username)}</div>
                        </div>
                        ${u.is_self ? `<span style="font-size:10px;color:var(--text3);">${t('rooms.itsYou')}</span>` : ''}
                    </div>`;
                });
            }

            // Channels
            if (data.channels && data.channels.length) {
                html += `<div class="search-section-label">${t('rooms.channels')}</div>`;
                data.channels.forEach(ch => {
                    html += `<div class="search-result-item" onclick="joinAndOpenChannel('${esc(ch.invite_code)}', ${ch.id})" style="cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="var(--accent)" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
                        <div class="room-body">
                            <div style="font-weight:700;font-size:13px;">${esc(ch.name)}</div>
                            <div style="font-size:11px;color:var(--text3);">${ch.subscriber_count} ${t('rooms.subscribers')}</div>
                        </div>
                    </div>`;
                });
            }

            // My chats
            if (data.chats && data.chats.length) {
                html += `<div class="search-section-label">${t('rooms.myChats')}</div>`;
                data.chats.forEach(c => {
                    html += `<div class="search-result-item" onclick="openRoom(${c.id})" style="cursor:pointer;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="var(--text2)" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
                        <div class="room-body">
                            <div style="font-weight:700;font-size:13px;">${esc(c.name)}</div>
                        </div>
                    </div>`;
                });
            }

            if (!html) html = `<div style="padding:12px;color:var(--text3);font-size:12px;">${t('rooms.nothingFound')}</div>`;

            resultsEl.innerHTML = html;
            resultsEl.style.display = '';
        } catch (e) {
            console.warn('Global search error:', e);
        }
    }, 400);
}

export async function joinAndOpenChannel(inviteCode, channelId) {
    try {
        await api('POST', `/api/channels/join/${inviteCode}`);
        await loadMyRooms();
        window.openRoom(channelId);
        const _gsi = document.getElementById('global-search-input');
        if (_gsi) _gsi.value = '';
        const _gsr = document.getElementById('global-search-results');
        if (_gsr) _gsr.style.display = 'none';
    } catch(e) { alert(e.message); }
}
