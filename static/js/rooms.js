// static/js/rooms.js
// ============================================================================
// Управление комнатами:
//   - Федеративное вступление без регистрации
//   - Авто-обнаружение комнат других узлов
//   - Мультихоп: вступление через промежуточный узел (A → B → C)
// ============================================================================

import { $, api, esc, openModal, closeModal, showAlert } from './utils.js';
import { showWelcome, showChatScreen } from './ui.js';
import { connectWS } from './chat/chat.js';
import { eciesEncrypt, getRoomKey, setRoomKey } from './crypto.js';

let _peerRoomsCache = {};
let _discoveryTimer = null;

// Периодически запрашивает у сервера свежий список комнат от соседних узлов.
export function startRoomDiscovery() {
    _discoverPeerRooms();
    _discoveryTimer = setInterval(_discoverPeerRooms, 20_000);
}

async function _discoverPeerRooms() {
    const S = window.AppState;
    if (!S.user) return;

    try {
        await api('POST', '/api/peers/refresh-rooms');
        const data      = await api('GET', '/api/peers/public-rooms');
        const peerRooms = data.rooms || [];

        let hasChanges = false;
        for (const room of peerRooms) {
            const key = `${room.peer_ip}:${room.peer_port}:${room.id}`;
            if (!_peerRoomsCache[key]) {
                _peerRoomsCache[key] = true;
                hasChanges = true;
            }
        }

        const fedRoomsBefore = S.rooms.filter(r => r.is_federated && r._discovery);
        if (fedRoomsBefore.length !== peerRooms.length) hasChanges = true;

        if (hasChanges) await _refreshRoomsQuiet();
    } catch { }
}

async function _refreshRoomsQuiet() {
    const S         = window.AppState;
    const currentId = S.currentRoom?.id;

    try {
        const [localData, fedData] = await Promise.allSettled([
            api('GET', '/api/rooms/my'),
            api('GET', '/api/federation/my-rooms'),
        ]);

        const localRooms = localData.status === 'fulfilled' ? (localData.value.rooms || []) : [];
        const fedRooms   = fedData.status   === 'fulfilled' ? (fedData.value.rooms   || []) : [];

        S.rooms = [...localRooms, ...fedRooms];

        if (currentId !== undefined) {
            const updated = S.rooms.find(r => r.id === currentId);
            if (updated) S.currentRoom = updated;
        }

        renderRoomsList();
    } catch { }
}

// ══════════════════════════════════════════════════════════════════════════════
// Основные операции с комнатами
// ══════════════════════════════════════════════════════════════════════════════

export async function loadMyRooms() {
    try {
        const [localData, fedData] = await Promise.allSettled([
            api('GET', '/api/rooms/my'),
            api('GET', '/api/federation/my-rooms'),
        ]);

        const localRooms = localData.status === 'fulfilled' ? (localData.value.rooms || []) : [];
        const fedRooms   = fedData.status   === 'fulfilled' ? (fedData.value.rooms   || []) : [];

        window.AppState.rooms = [...localRooms, ...fedRooms];
        renderRoomsList();
    } catch { }
}

export function renderRoomsList() {
    const el = $('rooms-list');
    const S  = window.AppState;

    if (!S.rooms.length) {
        el.innerHTML = '<div style="padding:12px 16px;color:var(--text3);font-size:12px;font-family:var(--mono);">Нет комнат — создайте или вступите</div>';
        return;
    }

    el.innerHTML = S.rooms.map(r => {
        const isFed  = r.is_federated;
        const icon   = isFed ? '🌐' : (r.is_private ? '🔒' : '💬');
        const fedTag = isFed
            ? `<div style="font-size:10px;color:var(--text3);font-family:var(--mono);">${esc(r.peer_ip || '')}</div>`
            : '';

        return `
        <div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}"
             onclick="window.openRoom(${r.id})" data-room="${r.id}">
          <div class="room-icon">${icon}</div>
          <div style="flex:1;min-width:0;">
            <div class="room-name">${esc(r.name)}</div>
            <div class="room-meta">${r.member_count} участн. · ${r.online_count} онлайн</div>
            ${fedTag}
          </div>
          ${r.online_count > 0 ? '<div class="online-dot"></div>' : ''}
        </div>`;
    }).join('');
}

/**
 * Гарантирует наличие x25519_public_key в AppState.user.
 * Если поле отсутствует (например, после входа по паролю), подтягивает
 * актуальные данные пользователя с сервера.
 * @returns {Promise<string|null>} pubkey hex или null
 */
async function _ensureUserPubkey() {
    const S = window.AppState;

    // 1. Уже есть в AppState
    if (S.user?.x25519_public_key) return S.user.x25519_public_key;

    // 2. Извлекаем из приватного JWK — надёжнее любого сетевого запроса.
    const privJwkStr = S.x25519PrivateKey || localStorage.getItem('vortex_x25519_priv');
    if (privJwkStr) {
        try {
            const jwk = JSON.parse(privJwkStr);
            if (jwk.x) {
                // base64url → hex
                const b64 = jwk.x.replace(/-/g, '+').replace(/_/g, '/');
                const binary = atob(b64);
                const hex = Array.from(binary, c => c.charCodeAt(0).toString(16).padStart(2, '0')).join('');
                if (S.user) S.user.x25519_public_key = hex;
                console.info('🔑 x25519_public_key восстановлен из локального JWK:', hex.slice(0, 16) + '...');
                return hex;
            }
        } catch (e) {
            console.warn('_ensureUserPubkey: не удалось извлечь pubkey из JWK:', e.message);
        }
    }

    // 3. Последний резерв — обновить данные с сервера (если сервер возвращает pubkey)
    try {
        const fresh = await api('GET', '/api/authentication/me');
        S.user = { ...S.user, ...fresh };
        if (fresh.display_name) {
            const sbName = document.getElementById('sb-name');
            if (sbName) sbName.textContent = fresh.display_name || fresh.username;
        }
    } catch (e) {
        console.warn('_ensureUserPubkey: не удалось обновить данные пользователя:', e.message);
    }

    return S.user?.x25519_public_key || null;
}

// При создании комнаты генерируем ключ комнаты локально,
// шифруем его под свой X25519 публичный ключ и отправляем на сервер.
// Сервер хранит только зашифрованную копию ключа.
export async function createRoom() {
    try {
        // Получаем pubkey, при необходимости обновляя данные пользователя
        const myPubkey = await _ensureUserPubkey();

        if (!myPubkey) {
            throw new Error(
                'X25519 публичный ключ не найден. ' +
                'Убедитесь, что вы зарегистрировались в этом браузере, ' +
                'или импортируйте резервную копию ключа в профиле.'
            );
        }

        const roomKeyBytes = crypto.getRandomValues(new Uint8Array(32));
        const encryptedKey = await eciesEncrypt(roomKeyBytes, myPubkey);

        const data = await api('POST', '/api/rooms', {
            name:               $('cr-name').value.trim(),
            description:        $('cr-desc').value.trim(),
            is_private:         $('cr-private').checked,
            encrypted_room_key: encryptedKey,
        });

        setRoomKey(data.id, roomKeyBytes);
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
        const isFed = S.currentRoom.is_federated;

        if (isFed) {
            await api('DELETE', `/api/federation/leave/${S.currentRoom.id}`);
        } else {
            await api('DELETE', `/api/rooms/${S.currentRoom.id}/leave`);
        }

        if (S.ws) {
            S.ws.onclose = null;
            if (S.ws._ping) clearInterval(S.ws._ping);
            S.ws.close();
            S.ws = null;
        }

        S.rooms = S.rooms.filter(r => r.id !== S.currentRoom.id);
        S.currentRoom = null;
        renderRoomsList();
        closeModal('members-modal');
        showWelcome();
    } catch (e) {
        alert(e.message);
    }
}

// ─── Публичные комнаты ────────────────────────────────────────────────────────

function _renderPublicRoomRow(r, isPeer) {
    const peerBadge = isPeer
        ? `<div style="font-size:10px;color:var(--text3);font-family:var(--mono);margin-top:2px;">
               🌐 ${esc(r.peer_name || r.peer_ip)}
           </div>`
        : '';

    const joinHandler = isPeer
        ? `window.joinPublicRoom(${r.id},'${r.invite_code}','${r.peer_ip}',${r.peer_port})`
        : `window.joinPublicRoom(${r.id},'${r.invite_code}')`;

    return `
      <div style="padding:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;">
        <div style="font-size:24px;">${r.is_private ? '🔒' : '💬'}</div>
        <div style="flex:1;">
          <div style="font-weight:700;">${esc(r.name)}</div>
          <div style="font-size:12px;color:var(--text2);font-family:var(--mono);">${r.member_count} участников</div>
          ${peerBadge}
        </div>
        <button class="btn btn-primary btn-sm" onclick="${joinHandler}">Вступить</button>
      </div>`;
}

export async function loadPublicRooms() {
    openModal('public-modal');

    const listEl = $('public-list');
    listEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text2);">Загрузка...</div>';

    try {
        await api('POST', '/api/peers/refresh-rooms').catch(() => {});

        const [localData, peerData] = await Promise.allSettled([
            api('GET', '/api/rooms/public'),
            api('GET', '/api/peers/public-rooms'),
        ]);

        const localRooms = localData.status === 'fulfilled' ? (localData.value.rooms || []) : [];
        const peerRooms  = peerData.status  === 'fulfilled' ? (peerData.value.rooms  || []) : [];

        if (!localRooms.length && !peerRooms.length) {
            listEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text2);">Нет публичных комнат</div>';
            return;
        }

        let html = '';

        if (localRooms.length) {
            html += `<div style="padding:8px 12px;font-size:11px;font-weight:700;color:var(--text3);
                         font-family:var(--mono);text-transform:uppercase;letter-spacing:.05em;
                         background:var(--bg2);border-bottom:1px solid var(--border);">
                         📍 Этот узел
                     </div>`;
            html += localRooms.map(r => _renderPublicRoomRow(r, false)).join('');
        }

        if (peerRooms.length) {
            html += `<div style="padding:8px 12px;font-size:11px;font-weight:700;color:var(--text3);
                         font-family:var(--mono);text-transform:uppercase;letter-spacing:.05em;
                         background:var(--bg2);border-bottom:1px solid var(--border);">
                         🌐 Другие узлы (${peerData.value?.peers || 0} пиров) · без регистрации
                     </div>`;
            html += peerRooms.map(r => _renderPublicRoomRow(r, true)).join('');
        }

        listEl.innerHTML = html;

    } catch (e) {
        listEl.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text2);">Ошибка: ${esc(e.message)}</div>`;
    }
}

// ─── Вступление в комнату ─────────────────────────────────────────────────────

export async function joinPublicRoom(id, code, peerIp, peerPort) {
    try {
        if (peerIp && peerPort) {
            closeModal('public-modal');

            const btn = document.querySelector(`button[onclick*="${code}"]`);
            if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

            let data;
            try {
                data = await api('POST', '/api/peers/federated-join', {
                    invite_code: code,
                    peer_ip:     peerIp,
                    peer_port:   peerPort,
                });
            } catch (directErr) {
                console.warn('Direct federated-join failed, trying multihop:', directErr.message);
                data = await _tryMultihopJoin(code, peerIp, peerPort);

                if (!data) {
                    alert(`Не удалось вступить в комнату:\n${directErr.message}`);
                    if (btn) { btn.disabled = false; btn.textContent = 'Вступить'; }
                    return;
                }
            }

            const room = data.room;
            if (!window.AppState.rooms.find(r => r.id === room.id)) {
                window.AppState.rooms.unshift(room);
            }

            renderRoomsList();
            window.openRoom(room.id);
            return;
        }

        await api('POST', `/api/rooms/join/${code}`);
        await loadMyRooms();
        closeModal('public-modal');
        window.openRoom(id);

    } catch (e) {
        alert(e.message);
    }
}

async function _tryMultihopJoin(code, targetIp, targetPort) {
    const S     = window.AppState;
    const peers = S.peers || [];

    for (const peer of peers) {
        if (peer.ip === targetIp) continue;
        try {
            console.log(`🔀 Multihop: пробуем через ${peer.ip}:${peer.port} → ${targetIp}:${targetPort}`);
            const data = await api('POST', '/api/peers/multihop-join', {
                invite_code:  code,
                target_ip:    targetIp,
                target_port:  targetPort,
                via_ip:       peer.ip,
                via_port:     peer.port,
            });
            console.log(`✅ Multihop успешен через ${peer.ip}`);
            return data;
        } catch (e) {
            console.warn(`Multihop через ${peer.ip} не удался:`, e.message);
        }
    }

    return null;
}

// ─── Вспомогательные функции ──────────────────────────────────────────────────

export function getRoomWsPath(room) {
    return room.is_federated ? `/ws/fed/${room.id}` : `/ws/${room.id}`;
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

    if (S.currentRoom.is_federated) {
        $('members-list').innerHTML = '<div style="padding:16px;color:var(--text2);font-size:13px;">🌐 Федеративная комната — список участников недоступен</div>';
        return;
    }

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
    if (!S.currentRoom || S.currentRoom.is_federated) return;
    try {
        const data = await api('GET', `/api/rooms/${S.currentRoom.id}`);
        S.currentRoom = data;
        S.rooms = S.rooms.map(r => r.id === data.id ? data : r);
        renderRoomsList();
        $('chat-room-meta').textContent = `${data.member_count} участников · ${data.online_count} онлайн`;
    } catch { }
}