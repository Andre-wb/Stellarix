// static/js/voice_channel.js
// ============================================================================
// Модуль голосовых каналов (persistent voice channels, Discord-style).
// Mesh-топология: каждый участник создает RTCPeerConnection с каждым другим.
// Сосуществует с 1:1 звонками из webrtc.js (те используют AppState.pc).
// ============================================================================

import { $, api, esc } from './utils.js';
import { renderRoomsList } from './rooms.js';
import { eciesEncrypt, setRoomKey } from './crypto.js';
import { t } from './i18n.js';

// ─── Voice channel state ─────────────────────────────────────────────────────

const _voicePeers = {};          // peerId -> { pc, audioEl, stream, speaking }
let _voiceRoomId     = null;     // id текущего голосового канала
let _voiceRoomName   = null;     // название текущего канала
let _voiceLocalStream = null;    // локальный MediaStream (audio)
let _voiceMuted      = false;
let _voiceSignalWs   = null;     // отдельный WS для голосового канала
let _voiceParticipants = [];     // массив участников [{user_id, username, display_name, avatar_emoji, avatar_url, is_muted}]
let _speakingIntervals = {};     // peerId -> intervalId
let _localSpeakingInterval = null;
let _localSpeakingCtx  = null;   // AudioContext для детекции голоса

// ICE серверы — используем те же что и webrtc.js
let _iceServers = [{ urls: 'stun:stun.l.google.com:19302' }];
let _iceLoaded  = false;

async function _loadIceServers() {
    if (_iceLoaded) return;
    try {
        const data = await api('GET', '/api/keys/ice-servers');
        if (data && data.ice_servers) {
            _iceServers = data.ice_servers;
        }
        _iceLoaded = true;
    } catch (e) {
        console.warn('[VoiceChannel] ICE servers fetch failed, using STUN fallback:', e);
    }
}

// ─── Join flow ───────────────────────────────────────────────────────────────

export async function joinVoiceChannel(roomId) {
    const S = window.AppState;
    if (_voiceRoomId === roomId) return; // already in this channel

    // Leave current voice channel if any
    if (_voiceRoomId) {
        await leaveVoiceChannel();
    }

    await _loadIceServers();

    // Get room info
    const room = S.rooms.find(r => r.id === roomId);
    if (!room) { console.error('[VoiceChannel] room not found:', roomId); return; }
    _voiceRoomName = room.name || t('voice.channel');

    // Get microphone access
    try {
        const _micId = (typeof window._getDeviceSetting === 'function') ? window._getDeviceSetting('audioInput') : '';
        const _audioC = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, sampleRate: 48000, channelCount: 1 };
        if (_micId) _audioC.deviceId = { exact: _micId };
        _voiceLocalStream = await navigator.mediaDevices.getUserMedia({ audio: _audioC, video: false });
    } catch (e) {
        alert(t('call.noMicAccess') + ': ' + e.message);
        return;
    }

    _voiceRoomId = roomId;
    _voiceMuted = false;

    // Call backend join API
    let participants = [];
    try {
        const resp = await api('POST', `/api/voice/${roomId}/join`);
        participants = resp.participants || [];
    } catch (e) {
        console.warn('[VoiceChannel] join API failed, continuing with signal only:', e.message);
    }

    // Connect signaling WebSocket
    _connectVoiceSignal(roomId);

    // Store participants
    _voiceParticipants = participants;

    // Show voice channel panel
    _showVoicePanel();
    _renderVoiceParticipants();

    // Start local speaking detection
    _startLocalSpeakingDetection();

    // Update sidebar
    renderRoomsList();

    console.log('[VoiceChannel] Joined room', roomId, 'participants:', participants.length);
}

// ─── Leave flow ──────────────────────────────────────────────────────────────

export async function leaveVoiceChannel() {
    if (!_voiceRoomId) return;

    const roomId = _voiceRoomId;

    // Close all peer connections
    for (const peerId of Object.keys(_voicePeers)) {
        _closePeer(peerId);
    }

    // Stop local speaking detection
    _stopLocalSpeakingDetection();

    // Stop local stream
    if (_voiceLocalStream) {
        _voiceLocalStream.getTracks().forEach(t => t.stop());
        _voiceLocalStream = null;
    }

    // Close signal WS
    if (_voiceSignalWs) {
        _voiceSignalWs.onclose = null;
        _voiceSignalWs.close();
        _voiceSignalWs = null;
    }

    // Call backend leave API
    try {
        await api('POST', `/api/voice/${roomId}/leave`);
    } catch (e) {
        console.warn('[VoiceChannel] leave API failed:', e.message);
    }

    _voiceRoomId = null;
    _voiceRoomName = null;
    _voiceMuted = false;
    _voiceParticipants = [];

    // Hide voice panel
    _hideVoicePanel();

    // Update sidebar
    renderRoomsList();

    console.log('[VoiceChannel] Left room', roomId);
}

// ─── Mute toggle ─────────────────────────────────────────────────────────────

export function toggleVoiceMute() {
    _voiceMuted = !_voiceMuted;
    if (_voiceLocalStream) {
        _voiceLocalStream.getAudioTracks().forEach(t => { t.enabled = !_voiceMuted; });
    }

    // Notify backend
    if (_voiceRoomId) {
        api('POST', `/api/voice/${_voiceRoomId}/mute`, { muted: _voiceMuted }).catch(() => {});
    }

    // Notify peers via signal
    _voiceSignal({ type: 'voice_mute', muted: _voiceMuted });

    // Update local participant state
    const me = _voiceParticipants.find(p => p.user_id === window.AppState.user?.id);
    if (me) me.is_muted = _voiceMuted;

    _updateMuteButton();
    _renderVoiceParticipants();
}

// ─── Signal WS for voice channel ─────────────────────────────────────────────

function _connectVoiceSignal(roomId) {
    if (_voiceSignalWs) {
        _voiceSignalWs.onclose = null;
        _voiceSignalWs.close();
    }

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const knockCookie = document.cookie.split(';').find(c => c.trim().startsWith('_vk='))?.split('=')[1];
    const knockParam = knockCookie ? `&knock=${knockCookie}` : '';

    _voiceSignalWs = new WebSocket(
        `${proto}://${location.host}/ws/signal/${roomId}?voice=1${knockParam}`
    );

    _voiceSignalWs.onopen = () => {
        console.log('[VoiceChannel] Signal WS open, room', roomId);
        // Announce ourselves
        _voiceSignal({
            type: 'voice_join',
            user_id: window.AppState.user?.id,
            username: window.AppState.user?.username,
            display_name: window.AppState.user?.display_name,
            avatar_emoji: window.AppState.user?.avatar_emoji,
            avatar_url: window.AppState.user?.avatar_url,
        });
    };

    _voiceSignalWs.onmessage = async (e) => {
        try {
            const msg = JSON.parse(e.data);
            await _handleVoiceSignal(msg);
        } catch (err) {
            console.error('[VoiceChannel] signal msg error:', err);
        }
    };

    _voiceSignalWs.onclose = (e) => {
        console.log('[VoiceChannel] Signal WS closed, code=', e.code);
        if (_voiceRoomId === roomId && e.code !== 1000) {
            // Reconnect after delay
            setTimeout(() => {
                if (_voiceRoomId === roomId) _connectVoiceSignal(roomId);
            }, 3000);
        }
    };

    _voiceSignalWs.onerror = (err) => {
        console.error('[VoiceChannel] Signal WS error:', err);
    };
}

function _voiceSignal(msg) {
    if (_voiceSignalWs?.readyState === WebSocket.OPEN) {
        _voiceSignalWs.send(JSON.stringify(msg));
    }
}

// ─── Handle incoming voice signals ──────────────────────────────────────────

async function _handleVoiceSignal(msg) {
    const S = window.AppState;
    const from = msg.from || msg.user_id;

    // Ignore messages from self
    if (from === S.user?.id) return;

    switch (msg.type) {
        case 'voice_join': {
            // New participant joined — add them and create peer connection
            _addParticipant({
                user_id: from,
                username: msg.username,
                display_name: msg.display_name,
                avatar_emoji: msg.avatar_emoji,
                avatar_url: msg.avatar_url,
                is_muted: false,
            });
            _renderVoiceParticipants();

            // Create offer for this new peer
            await _createPeerOffer(from);
            break;
        }

        case 'voice_leave': {
            _removeParticipant(from);
            _closePeer(from);
            _renderVoiceParticipants();
            break;
        }

        case 'voice_mute': {
            const p = _voiceParticipants.find(p => p.user_id === from);
            if (p) p.is_muted = !!msg.muted;
            _renderVoiceParticipants();
            break;
        }

        case 'voice_peers': {
            // Backend tells us who is in the channel — connect to each
            const peers = msg.peers || [];
            for (const peer of peers) {
                if (peer.user_id === S.user?.id) continue;
                _addParticipant(peer);
                if (!_voicePeers[peer.user_id]) {
                    await _createPeerOffer(peer.user_id);
                }
            }
            _renderVoiceParticipants();
            break;
        }

        case 'voice_offer': {
            await _handlePeerOffer(from, msg.sdp);
            break;
        }

        case 'voice_answer': {
            await _handlePeerAnswer(from, msg.sdp);
            break;
        }

        case 'voice_ice': {
            await _handlePeerIce(from, msg.candidate);
            break;
        }

        default:
            // Forward standard signal types (offer/answer/ice) if they come through
            if (msg.type === 'offer' && _voiceRoomId) {
                await _handlePeerOffer(from, msg.sdp);
            } else if (msg.type === 'answer' && _voiceRoomId) {
                await _handlePeerAnswer(from, msg.sdp);
            } else if (msg.type === 'ice' && _voiceRoomId) {
                await _handlePeerIce(from, msg.candidate);
            }
    }
}

// ─── Peer Connection management (mesh) ───────────────────────────────────────

function _createPeerConnection(peerId) {
    const config = { iceServers: _iceServers };
    const pc = new RTCPeerConnection(config);

    // Add local audio tracks
    if (_voiceLocalStream) {
        _voiceLocalStream.getTracks().forEach(t => pc.addTrack(t, _voiceLocalStream));
    }

    pc.onicecandidate = (e) => {
        if (!e.candidate) return;
        _voiceSignal({
            type: 'voice_ice',
            to: peerId,
            candidate: e.candidate.toJSON(),
        });
    };

    pc.ontrack = (e) => {
        console.log('[VoiceChannel] ontrack from peer', peerId, e.track.kind);
        const stream = e.streams[0] || new MediaStream([e.track]);

        // Create or reuse audio element
        if (!_voicePeers[peerId]) {
            _voicePeers[peerId] = {};
        }
        _voicePeers[peerId].stream = stream;

        let audioEl = _voicePeers[peerId].audioEl;
        if (!audioEl) {
            audioEl = document.createElement('audio');
            audioEl.autoplay = true;
            audioEl.id = `vc-audio-${peerId}`;
            const container = document.getElementById('vc-audio-container');
            if (container) container.appendChild(audioEl);
            _voicePeers[peerId].audioEl = audioEl;
        }
        audioEl.srcObject = stream;
        // Apply saved output device
        const _outId = (typeof window._getDeviceSetting === 'function') ? window._getDeviceSetting('audioOutput') : '';
        if (_outId && typeof audioEl.setSinkId === 'function') audioEl.setSinkId(_outId).catch(() => {});

        // Start speaking detection for this peer
        _startPeerSpeakingDetection(peerId, stream);
    };

    pc.onconnectionstatechange = () => {
        const state = pc.connectionState;
        console.log(`[VoiceChannel] peer ${peerId} state: ${state}`);
        if (['failed', 'closed', 'disconnected'].includes(state)) {
            // Peer disconnected
            if (state === 'failed') {
                _closePeer(peerId);
                _removeParticipant(peerId);
                _renderVoiceParticipants();
            }
        }
    };

    if (!_voicePeers[peerId]) {
        _voicePeers[peerId] = {};
    }
    _voicePeers[peerId].pc = pc;

    return pc;
}

async function _createPeerOffer(peerId) {
    const pc = _createPeerConnection(peerId);
    try {
        const offer = await pc.createOffer({ offerToReceiveAudio: true });
        await pc.setLocalDescription(offer);
        _voiceSignal({
            type: 'voice_offer',
            to: peerId,
            sdp: offer.sdp,
        });
    } catch (e) {
        console.error('[VoiceChannel] createOffer failed for', peerId, e);
    }
}

async function _handlePeerOffer(peerId, sdp) {
    let peer = _voicePeers[peerId];
    if (!peer?.pc || peer.pc.signalingState === 'closed') {
        _createPeerConnection(peerId);
        peer = _voicePeers[peerId];
    }

    try {
        await peer.pc.setRemoteDescription({ type: 'offer', sdp });

        // Flush pending ICE candidates
        if (peer._pendingIce) {
            for (const c of peer._pendingIce) {
                try { await peer.pc.addIceCandidate(c); } catch {}
            }
            peer._pendingIce = [];
        }

        const answer = await peer.pc.createAnswer();
        await peer.pc.setLocalDescription(answer);
        _voiceSignal({
            type: 'voice_answer',
            to: peerId,
            sdp: answer.sdp,
        });
    } catch (e) {
        console.error('[VoiceChannel] handleOffer failed for', peerId, e);
    }
}

async function _handlePeerAnswer(peerId, sdp) {
    const peer = _voicePeers[peerId];
    if (!peer?.pc) return;
    try {
        if (peer.pc.signalingState !== 'stable') {
            await peer.pc.setRemoteDescription({ type: 'answer', sdp });

            // Flush pending ICE candidates
            if (peer._pendingIce) {
                for (const c of peer._pendingIce) {
                    try { await peer.pc.addIceCandidate(c); } catch {}
                }
                peer._pendingIce = [];
            }
        }
    } catch (e) {
        console.error('[VoiceChannel] handleAnswer failed for', peerId, e);
    }
}

async function _handlePeerIce(peerId, candidate) {
    const peer = _voicePeers[peerId];
    if (!peer) return;
    if (peer.pc?.remoteDescription) {
        try { await peer.pc.addIceCandidate(candidate); } catch (e) {
            console.warn('[VoiceChannel] ICE error:', e.message);
        }
    } else {
        // Queue for later
        if (!peer._pendingIce) peer._pendingIce = [];
        peer._pendingIce.push(candidate);
    }
}

function _closePeer(peerId) {
    const peer = _voicePeers[peerId];
    if (!peer) return;

    // Stop speaking detection
    if (_speakingIntervals[peerId]) {
        clearInterval(_speakingIntervals[peerId]);
        delete _speakingIntervals[peerId];
    }

    if (peer.pc) {
        peer.pc.onicecandidate = null;
        peer.pc.ontrack = null;
        peer.pc.onconnectionstatechange = null;
        peer.pc.close();
    }

    if (peer.audioEl) {
        peer.audioEl.srcObject = null;
        peer.audioEl.remove();
    }

    delete _voicePeers[peerId];
}

// ─── Participant management ──────────────────────────────────────────────────

function _addParticipant(info) {
    const existing = _voiceParticipants.find(p => p.user_id === info.user_id);
    if (!existing) {
        _voiceParticipants.push(info);
    } else {
        // Update info
        Object.assign(existing, info);
    }
}

function _removeParticipant(userId) {
    _voiceParticipants = _voiceParticipants.filter(p => p.user_id !== userId);
}

// ─── Speaking detection ──────────────────────────────────────────────────────

function _startLocalSpeakingDetection() {
    if (!_voiceLocalStream) return;

    try {
        _localSpeakingCtx = new (window.AudioContext || window.webkitAudioContext)();
        const analyser = _localSpeakingCtx.createAnalyser();
        const source = _localSpeakingCtx.createMediaStreamSource(_voiceLocalStream);
        source.connect(analyser);
        analyser.fftSize = 256;
        const data = new Uint8Array(analyser.frequencyBinCount);

        _localSpeakingInterval = setInterval(() => {
            analyser.getByteFrequencyData(data);
            const avg = data.reduce((a, b) => a + b, 0) / data.length;
            const speaking = avg > 15 && !_voiceMuted;

            const myId = window.AppState.user?.id;
            const card = document.querySelector(`.vc-participant[data-uid="${myId}"]`);
            if (card) {
                card.classList.toggle('speaking', speaking);
            }
        }, 100);
    } catch (e) {
        console.warn('[VoiceChannel] speaking detection init failed:', e);
    }
}

function _stopLocalSpeakingDetection() {
    if (_localSpeakingInterval) {
        clearInterval(_localSpeakingInterval);
        _localSpeakingInterval = null;
    }
    if (_localSpeakingCtx) {
        _localSpeakingCtx.close().catch(() => {});
        _localSpeakingCtx = null;
    }
}

function _startPeerSpeakingDetection(peerId, stream) {
    // Clear existing
    if (_speakingIntervals[peerId]) {
        clearInterval(_speakingIntervals[peerId]);
    }

    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const analyser = ctx.createAnalyser();
        const source = ctx.createMediaStreamSource(stream);
        source.connect(analyser);
        analyser.fftSize = 256;
        const data = new Uint8Array(analyser.frequencyBinCount);

        _speakingIntervals[peerId] = setInterval(() => {
            analyser.getByteFrequencyData(data);
            const avg = data.reduce((a, b) => a + b, 0) / data.length;
            const speaking = avg > 15;

            const card = document.querySelector(`.vc-participant[data-uid="${peerId}"]`);
            if (card) {
                card.classList.toggle('speaking', speaking);
            }
        }, 100);

        // Store context for cleanup
        if (_voicePeers[peerId]) {
            _voicePeers[peerId]._audioCtx = ctx;
        }
    } catch (e) {
        console.warn('[VoiceChannel] peer speaking detection failed:', e);
    }
}

// ─── UI: Voice Channel Panel ─────────────────────────────────────────────────

function _showVoicePanel() {
    const panel = document.getElementById('voice-channel-panel');
    if (!panel) return;

    // Hide other screens
    const welcome = document.getElementById('welcome-screen');
    const chat    = document.getElementById('chat-screen');
    if (welcome) welcome.classList.remove('active');
    if (chat)    chat.classList.remove('active');

    // Show voice panel as flex (overrides .screen display:none)
    panel.style.display = 'flex';
    panel.classList.add('active');

    _updateVoiceHeader();
    _updateMuteButton();
}

function _hideVoicePanel() {
    const panel = document.getElementById('voice-channel-panel');
    if (panel) {
        panel.style.display = 'none';
        panel.classList.remove('active');
    }

    // Show welcome screen
    const welcome = document.getElementById('welcome-screen');
    if (welcome) welcome.classList.add('active');
}

function _updateVoiceHeader() {
    const nameEl  = document.getElementById('vc-name');
    const countEl = document.getElementById('vc-count');

    if (nameEl) nameEl.textContent = _voiceRoomName || t('voice.channel');

    const total = _voiceParticipants.length + 1; // +1 for self
    const label = _pluralParticipants(total);
    if (countEl) countEl.textContent = `${total} ${label}`;
}

function _pluralParticipants(n) {
    return n === 1 ? 'participant' : 'participants';
}

function _renderVoiceParticipants() {
    const container = document.getElementById('vc-participants');
    if (!container) return;

    const S = window.AppState;
    const me = {
        user_id: S.user?.id,
        display_name: S.user?.display_name || S.user?.username || t('rooms.you'),
        avatar_emoji: S.user?.avatar_emoji || '',
        avatar_url: S.user?.avatar_url || '',
        is_muted: _voiceMuted,
        is_self: true,
    };

    const all = [me, ..._voiceParticipants];

    container.innerHTML = all.map(p => {
        const name = p.is_self ? t('rooms.you') : (p.display_name || p.username || 'Participant');
        const avatarHtml = p.avatar_url
            ? `<img src="${esc(p.avatar_url)}" alt="" class="vc-participant-avatar-img">`
            : `<span class="vc-participant-avatar-emoji">${esc(p.avatar_emoji || '')}</span>`;
        const mutedClass = p.is_muted ? ' muted' : '';

        return `
        <div class="vc-participant${mutedClass}" data-uid="${p.user_id}">
            <div class="vc-participant-avatar">
                ${avatarHtml}
                <div class="vc-speaking-ring"></div>
            </div>
            <div class="vc-participant-name">${esc(name)}</div>
            ${p.is_muted ? '<div class="vc-participant-muted-icon"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M8.03 12.27a3.98 3.98 0 0 0 3.7 3.7zM20 12h-2c0 1.29-.42 2.49-1.12 3.47l-1.44-1.44c.36-.59.56-1.28.56-2.02v-6c0-2.21-1.79-4-4-4s-4 1.79-4 4v.59L2.71 1.29 1.3 2.7l20 20 1.41-1.41-4.4-4.4A7.9 7.9 0 0 0 20 12M10 6c0-1.1.9-2 2-2s2 .9 2 2v6c0 .18-.03.35-.07.51L10 8.58V5.99Z"/><path d="M12 18c-3.31 0-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c.74-.09 1.45-.29 2.12-.57l-1.57-1.57c-.49.13-1.01.21-1.55.21"/></svg></div>' : ''}
        </div>`;
    }).join('');

    _updateVoiceHeader();
}

function _updateMuteButton() {
    const btn = document.getElementById('vc-mute-btn');
    if (!btn) return;

    if (_voiceMuted) {
        btn.classList.add('vc-btn-muted');
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M8.03 12.27a3.98 3.98 0 0 0 3.7 3.7zM20 12h-2c0 1.29-.42 2.49-1.12 3.47l-1.44-1.44c.36-.59.56-1.28.56-2.02v-6c0-2.21-1.79-4-4-4s-4 1.79-4 4v.59L2.71 1.29 1.3 2.7l20 20 1.41-1.41-4.4-4.4A7.9 7.9 0 0 0 20 12M10 6c0-1.1.9-2 2-2s2 .9 2 2v6c0 .18-.03.35-.07.51L10 8.58V5.99Z"/><path d="M12 18c-3.31 0-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c.74-.09 1.45-.29 2.12-.57l-1.57-1.57c-.49.13-1.01.21-1.55.21"/></svg><span>${t('voice.unmute')}</span>`;
    } else {
        btn.classList.remove('vc-btn-muted');
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M16 12V6c0-2.21-1.79-4-4-4S8 3.79 8 6v6c0 2.21 1.79 4 4 4s4-1.79 4-4m-6 0V6c0-1.1.9-2 2-2s2 .9 2 2v6c0 1.1-.9 2-2 2s-2-.9-2-2"/><path d="M18 12c0 3.31-2.69 6-6 6s-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c3.94-.49 7-3.86 7-7.93z"/></svg><span>${t('voice.mute')}</span>`;
    }
}

// ─── Create Voice Channel Modal ──────────────────────────────────────────────

export function showCreateVoiceModal() { showCreateVoiceChannelModal(); }

export function showCreateVoiceChannelModal() {
    if (typeof window.openModal === 'function') {
        window.openModal('create-voice-modal');
    } else {
        const modal = document.getElementById('create-voice-modal');
        if (modal) modal.classList.add('show');
    }
    setTimeout(() => {
        const inp = document.getElementById('vc-new-name');
        if (inp) inp.focus();
    }, 50);
}

export async function createVoiceChannel() {
    const nameInput = document.getElementById('vc-new-name');
    const name = nameInput?.value?.trim();
    if (!name) {
        const alertEl = document.getElementById('vc-create-alert');
        if (alertEl) {
            alertEl.textContent = t('rooms.enterName');
            alertEl.className = 'alert alert-error show';
        }
        return;
    }

    try {
        const S = window.AppState;
        const myPubkey = S.user?.x25519_public_key;
        if (!myPubkey) {
            throw new Error('X25519 public key not found');
        }

        // Generate and encrypt room key (required by /api/rooms endpoint)
        const roomKeyBytes = crypto.getRandomValues(new Uint8Array(32));
        const encryptedKey = await eciesEncrypt(roomKeyBytes, myPubkey);

        const data = await api('POST', '/api/rooms', {
            name: name,
            is_voice: true,
            encrypted_room_key: encryptedKey,
        });

        setRoomKey(data.id, roomKeyBytes);
        data.is_voice = true;
        data.voice_participants = [];
        window.AppState.rooms.push(data);
        renderRoomsList();

        // Close modal
        if (typeof window.closeModal === 'function') {
            window.closeModal('create-voice-modal');
        } else {
            const modal = document.getElementById('create-voice-modal');
            if (modal) modal.classList.remove('show');
        }
        if (nameInput) nameInput.value = '';

        // Auto-join
        await joinVoiceChannel(data.id);
    } catch (e) {
        const alertEl = document.getElementById('vc-create-alert');
        if (alertEl) {
            alertEl.textContent = e.message || t('spaces.createError');
            alertEl.className = 'alert alert-error show';
        }
    }
}

// ─── Public getters ──────────────────────────────────────────────────────────

export function getVoiceRoomId() {
    return _voiceRoomId;
}

export function isInVoiceChannel(roomId) {
    return _voiceRoomId === roomId;
}

export function getVoiceParticipantCount(roomId) {
    if (_voiceRoomId === roomId) {
        return _voiceParticipants.length + 1; // +1 for self
    }
    // Get from room data
    const room = window.AppState.rooms.find(r => r.id === roomId);
    return room?.voice_participants?.length || 0;
}

// ─── Sidebar connector bar (shows at bottom when in voice) ───────────────────

export function renderVoiceConnectorBar() {
    let bar = document.getElementById('vc-connector-bar');

    if (!_voiceRoomId) {
        if (bar) bar.style.display = 'none';
        return;
    }

    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'vc-connector-bar';
        const sidebar = document.getElementById('sidebar');
        const footer = sidebar?.querySelector('.sidebar-footer');
        if (footer) {
            sidebar.insertBefore(bar, footer);
        }
    }

    const total = _voiceParticipants.length + 1;
    bar.style.display = '';
    bar.innerHTML = `
        <div class="vcb-info">
            <div class="vcb-status">
                <div class="vcb-pulse"></div>
                <span>${t('nav.newVoice')}</span>
            </div>
            <div class="vcb-name">${esc(_voiceRoomName || '')}</div>
        </div>
        <div class="vcb-actions">
            <button class="vcb-btn ${_voiceMuted ? 'vcb-btn-muted' : ''}" onclick="toggleVoiceMute()" title="${_voiceMuted ? (typeof t==='function'?t('voice.unmuteMic'):'Unmute microphone') : (typeof t==='function'?t('voice.muteMic'):'Mute microphone')}">
                ${_voiceMuted
                    ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M8.03 12.27a3.98 3.98 0 0 0 3.7 3.7zM20 12h-2c0 1.29-.42 2.49-1.12 3.47l-1.44-1.44c.36-.59.56-1.28.56-2.02v-6c0-2.21-1.79-4-4-4s-4 1.79-4 4v.59L2.71 1.29 1.3 2.7l20 20 1.41-1.41-4.4-4.4A7.9 7.9 0 0 0 20 12M10 6c0-1.1.9-2 2-2s2 .9 2 2v6c0 .18-.03.35-.07.51L10 8.58V5.99Z"/><path d="M12 18c-3.31 0-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c.74-.09 1.45-.29 2.12-.57l-1.57-1.57c-.49.13-1.01.21-1.55.21"/></svg>'
                    : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M16 12V6c0-2.21-1.79-4-4-4S8 3.79 8 6v6c0 2.21 1.79 4 4 4s4-1.79 4-4m-6 0V6c0-1.1.9-2 2-2s2 .9 2 2v6c0 1.1-.9 2-2 2s-2-.9-2-2"/><path d="M18 12c0 3.31-2.69 6-6 6s-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c3.94-.49 7-3.86 7-7.93z"/></svg>'}
            </button>
            <button class="vcb-btn vcb-btn-leave" onclick="leaveVoiceChannel()" title="${typeof t==='function'?t('voice.disconnect'):'Disconnect'}">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08a.956.956 0 0 1-.29-.7c0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.11-.7-.28a11.27 11.27 0 0 0-2.67-1.85.996.996 0 0 1-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"/></svg>
            </button>
        </div>`;
}

