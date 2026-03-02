import { $, api, esc, fmtSize, openModal, closeModal, showAlert } from './utils.js';
import { showWelcome, showChatScreen } from './ui.js';
import { connectWS } from './chat/chat.js';      // ← ИСПРАВЛЕНО: было './chat.js'

export async function loadMyRooms() {
    try {
        const data = await api('GET', '/api/rooms/my');
        window.AppState.rooms = data.rooms;
        renderRoomsList();
    } catch { }
}

export function renderRoomsList() {
    const el = $('rooms-list');
    const S = window.AppState;
    if (!S.rooms.length) {
        el.innerHTML = '<div style="padding:12px 16px;color:var(--text3);font-size:12px;font-family:var(--mono);">Нет комнат — создайте или вступите</div>';
        return;
    }
    el.innerHTML = S.rooms.map(r => `
    <div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}"
         onclick="window.openRoom(${r.id})" data-room="${r.id}">
      <div class="room-icon">${r.is_private ? '🔒' : '💬'}</div>
      <div style="flex:1;min-width:0;">
        <div class="room-name">${esc(r.name)}</div>
        <div class="room-meta">${r.member_count} участн. · ${r.online_count} онлайн</div>
      </div>
      ${r.online_count > 0 ? '<div class="online-dot"></div>' : ''}
    </div>
  `).join('');
}

export async function createRoom() {
    try {
        const data = await api('POST', '/api/rooms', {
            name: $('cr-name').value.trim(),
            description: $('cr-desc').value.trim(),
            is_private: $('cr-private').checked,
        });
        window.AppState.rooms.unshift(data);
        renderRoomsList();
        closeModal('create-room-modal');
        window.openRoom(data.id);
        $('cr-name').value = '';
        $('cr-desc').value = '';
    } catch (e) {
        showAlert('cr-alert', e.message);
    }
}

export async function joinRoom() {
    const code = $('join-code').value.trim().toUpperCase();
    if (code.length !== 8) {
        showAlert('join-alert', 'Введите 8-символьный код');
        return;
    }
    try {
        const data = await api('POST', `/api/rooms/join/${code}`);
        const room = data.room;
        if (!window.AppState.rooms.find(r => r.id === room.id)) {
            window.AppState.rooms.unshift(room);
        }
        renderRoomsList();
        closeModal('join-modal');
        window.openRoom(room.id);
        $('join-code').value = '';
    } catch (e) {
        showAlert('join-alert', e.message);
    }
}

export async function leaveRoom() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    try {
        await api('DELETE', `/api/rooms/${S.currentRoom.id}/leave`);
        if (S.ws) { S.ws.onclose = null; if (S.ws._ping) clearInterval(S.ws._ping); S.ws.close(); S.ws = null; }
        S.rooms = S.rooms.filter(r => r.id !== S.currentRoom.id);
        S.currentRoom = null;
        renderRoomsList();
        closeModal('members-modal');
        showWelcome();
    } catch (e) {
        alert(e.message);
    }
}

export async function loadPublicRooms() {
    openModal('public-modal');
    try {
        const data = await api('GET', '/api/rooms/public');
        $('public-list').innerHTML = data.rooms.length ? data.rooms.map(r => `
      <div style="padding:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;">
        <div style="font-size:24px;">${r.is_private ? '🔒' : '💬'}</div>
        <div style="flex:1;">
          <div style="font-weight:700;">${esc(r.name)}</div>
          <div style="font-size:12px;color:var(--text2);font-family:var(--mono);">${r.member_count} участников</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="window.joinPublicRoom(${r.id},'${r.invite_code}')">Вступить</button>
      </div>
    `).join('') : '<div style="padding:24px;text-align:center;color:var(--text2);">Нет публичных комнат</div>';
    } catch { }
}

export async function joinPublicRoom(id, code) {
    try {
        await api('POST', `/api/rooms/join/${code}`);
        await loadMyRooms();
        closeModal('public-modal');
        window.openRoom(id);
    } catch (e) {
        alert(e.message);
    }
}

export function showCreateRoomModal() {
    openModal('create-room-modal');
    setTimeout(() => $('cr-name').focus(), 50);
}

export function showJoinModal() {
    openModal('join-modal');
    setTimeout(() => $('join-code').focus(), 50);
}

export function copyInviteCode() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    navigator.clipboard.writeText(S.currentRoom.invite_code).then(() => {
        $('modal-invite-code').style.color = 'var(--green)';
        setTimeout(() => $('modal-invite-code').style.color = '', 1000);
    });
}

export async function showMembersModal() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    openModal('members-modal');
    $('modal-invite-code').textContent = S.currentRoom.invite_code;
    try {
        const data = await api('GET', `/api/rooms/${S.currentRoom.id}/members`);
        $('members-list').innerHTML = data.members.map(m => `
      <div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);">
        <div class="avatar">${esc(m.avatar_emoji)}</div>
        <div style="flex:1;">
          <div style="font-weight:700;">${esc(m.display_name)}</div>
          <div style="font-size:11px;color:var(--text2);font-family:var(--mono);">@${esc(m.username)} · ${m.role}</div>
        </div>
        <div style="width:8px;height:8px;border-radius:50%;background:${m.is_online ? 'var(--green)' : 'var(--text3)'};"></div>
      </div>
    `).join('');
    } catch { }
}

export async function updateRoomMeta() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    try {
        const data = await api('GET', `/api/rooms/${S.currentRoom.id}`);
        S.currentRoom = data;
        S.rooms = S.rooms.map(r => r.id === data.id ? data : r);
        renderRoomsList();
        $('chat-room-meta').textContent = `${data.member_count} участников · ${data.online_count} онлайн`;
    } catch { }
}