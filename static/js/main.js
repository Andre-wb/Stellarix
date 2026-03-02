import { $, loadCsrfToken, api, openModal, closeModal } from './utils.js';
import { checkSession }    from './auth.js';
import { startPeerPolling } from './peers.js';
import { showWelcome }     from './ui.js';

import * as auth        from './auth.js';
import * as rooms       from './rooms.js';
import * as peers       from './peers.js';
import * as webrtc      from './webrtc.js';
import * as ui          from './ui.js';
import * as chat        from './chat/chat.js';
import * as fileUpload  from './chat/file-upload.js';
import * as imageViewer from './chat/image-viewer.js';

window.AppState = {
    user:          null,
    rooms:         [],
    currentRoom:   null,
    token:         null,
    ws:            null,
    signalWs:      null,
    peers:         [],
    peersInterval: null,
    typingTimeout: null,
    selectedEmoji: '👤',
    pc:            null,
    localStream:   null,
    isMuted:       false,
    isCamOff:      false,
    nodePublicKey: null,
    sessionKeys:   {},
    csrfToken:     null,
};

Object.assign(window, auth, rooms, chat, peers, webrtc, ui, fileUpload, imageViewer);
window.openModal  = openModal;
window.closeModal = closeModal;

window.bootApp = async function bootApp() {
    $('auth-screen').style.display = 'none';
    $('app').style.display         = 'flex';

    $('sb-avatar').textContent = AppState.user.avatar_emoji || '👤';
    $('sb-name').textContent   = AppState.user.display_name || AppState.user.username;
    $('sb-phone').textContent  = AppState.user.phone;

    await loadCsrfToken();
    setInterval(loadCsrfToken, 600_000);

    try {
        const d = await api('GET', '/api/keys/pubkey');
        AppState.nodePublicKey = d.pubkey_hex;
        console.log('🔑 X25519 pubkey:', AppState.nodePublicKey.slice(0, 16) + '...');
    } catch {}

    await rooms.loadMyRooms();
    startPeerPolling();

    if (typeof imageViewer.initImageViewer === 'function') {
        imageViewer.initImageViewer();
    }

    showWelcome();
};

document.querySelectorAll('.modal-overlay').forEach(el => {
    el.addEventListener('click', e => {
        if (e.target === el) el.classList.remove('show');
    });
});

document.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const loginForm = document.getElementById('login-form');
    if (!loginForm || loginForm.style.display === 'none') return;
    const focused = document.activeElement;
    if (focused === document.getElementById('l-login') ||
        focused === document.getElementById('l-pass')) {
        window.doLogin?.();
    }
});

window.addEventListener('DOMContentLoaded', checkSession);