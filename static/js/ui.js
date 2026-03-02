import { $ } from './utils.js';
import { renderRoomsList } from './rooms.js';
import { connectWS } from './chat/chat.js';      // ← ИСПРАВЛЕНО: было './chat.js'
import { connectSignal } from './webrtc.js';

export function showWelcome() {
    $('welcome-screen').classList.add('active');
    $('chat-screen').classList.remove('active');
    $('welcome-screen').style.display = 'flex';
    $('chat-screen').style.display = 'none';
    window.AppState.currentRoom = null;
    renderRoomsList();
    $('nav-welcome').classList.add('active');
}

export function showChatScreen() {
    $('welcome-screen').style.display = 'none';
    $('chat-screen').style.display = 'flex';
    $('chat-screen').classList.add('active');
    $('welcome-screen').classList.remove('active');
    $('nav-welcome').classList.remove('active');
}

export function openRoom(id) {
    const S = window.AppState;
    const room = S.rooms.find(r => r.id === id);
    if (!room) return;
    S.currentRoom = room;
    if (S.ws) {
        S.ws.onclose = null;                        // не триггерим авто-реконнект
        if (S.ws._ping) clearInterval(S.ws._ping);  // убиваем утёкший интервал
        S.ws.close();
        S.ws = null;
    }
    showChatScreen();
    $('messages-container').innerHTML = '';
    $('chat-room-name').textContent = room.name;
    $('chat-room-meta').textContent = `${room.member_count} участников · ${room.online_count} онлайн`;
    renderRoomsList();
    connectWS(id);
    connectSignal(id);
}

export function showProfileModal() {
    const S = window.AppState;
    if (!S.user) return;
    $('prof-phone').textContent = S.user.phone;
    $('prof-username').textContent = '@' + S.user.username;
    $('prof-created').textContent = new Date(S.user.created_at).toLocaleDateString('ru');
    window.openModal('profile-modal');
}