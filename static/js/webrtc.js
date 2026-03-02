import { $ } from './utils.js';

const ICE_SERVERS = [{ urls: 'stun:stun.l.google.com:19302' }];

let _isHangingUp = false;
let _incomingCallFrom = null;

export function connectSignal(roomId) {
    const S = window.AppState;

    if (S.signalWs) {
        S.signalWs.onclose = null;  // не триггерим реконнект при ручном закрытии
        S.signalWs.close();
        S.signalWs = null;
    }

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    S.signalWs = new WebSocket(`${proto}://${location.host}/ws/signal/${roomId}`);

    S.signalWs.onopen = () => console.log('Signal WS открыт, комната', roomId);

    S.signalWs.onmessage = async e => {
        try {
            await handleSignal(JSON.parse(e.data));
        } catch (err) {
            console.error('Signal msg error:', err);
        }
    };

    S.signalWs.onclose = e => {
        console.log('Signal WS закрыт, code=', e.code);
        S.signalWs = null;
        if (S.currentRoom?.id === roomId && e.code !== 1000) {
            setTimeout(() => {
                if (S.currentRoom?.id === roomId && !S.signalWs) connectSignal(roomId);
            }, 3000);
        }
    };

    S.signalWs.onerror = err => console.error('Signal WS error:', err);
}
function waitForSignalOpen(timeout = 5000) {
    return new Promise((resolve, reject) => {
        const S = window.AppState;
        if (!S.signalWs) { reject(new Error('signalWs не создан')); return; }
        if (S.signalWs.readyState === WebSocket.OPEN) { resolve(); return; }
        const tid = setTimeout(() => reject(new Error('Signal WS timeout')), timeout);
        S.signalWs.addEventListener('open',  () => { clearTimeout(tid); resolve(); }, { once: true });
        S.signalWs.addEventListener('close', () => { clearTimeout(tid); reject(new Error('WS закрылся')); }, { once: true });
    });
}

function signal(msg) {
    const S = window.AppState;
    if (S.signalWs?.readyState === WebSocket.OPEN) {
        S.signalWs.send(JSON.stringify(msg));
    } else {
        console.warn('signal(): WS не готов, тип=', msg.type);
    }
}

export async function startVoiceCall() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    if (!S.signalWs || S.signalWs.readyState === WebSocket.CLOSED) {
        connectSignal(S.currentRoom.id);
    }
    try {
        await waitForSignalOpen();
    } catch (e) {
        alert('Нет соединения с сигнальным сервером: ' + e.message);
        return;
    }

    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (e) {
        alert('Нет доступа к микрофону: ' + e.message);
        return;
    }

    $('call-peer-name').textContent = S.currentRoom.name;
    $('call-peer-avatar').textContent = '💬';
    $('call-status').textContent = 'Вызов...';
    $('local-video').srcObject = S.localStream;
    $('call-overlay').classList.add('show');
    _isHangingUp = false;

    S.pc = createPeerConnection();
    S.localStream.getTracks().forEach(t => S.pc.addTrack(t, S.localStream));

    const offer = await S.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: false });
    await S.pc.setLocalDescription(offer);

    signal({ type: 'invite' });
    await new Promise(r => setTimeout(r, 50));
    signal({ type: 'offer', sdp: offer.sdp });
}

export async function startVideoCall() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    if (!S.signalWs || S.signalWs.readyState === WebSocket.CLOSED) {
        connectSignal(S.currentRoom.id);
    }
    try {
        await waitForSignalOpen();
    } catch (e) {
        alert('Нет соединения с сигнальным сервером: ' + e.message);
        return;
    }

    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    } catch (e) {
        alert('Нет доступа к камере/микрофону: ' + e.message);
        return;
    }

    $('call-peer-name').textContent = S.currentRoom.name;
    $('call-peer-avatar').textContent = '💬';
    $('call-status').textContent = 'Видеозвонок...';
    $('local-video').srcObject = S.localStream;
    $('call-overlay').classList.add('show');
    _isHangingUp = false;

    S.pc = createPeerConnection();
    S.localStream.getTracks().forEach(t => S.pc.addTrack(t, S.localStream));

    const offer = await S.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
    await S.pc.setLocalDescription(offer);

    signal({ type: 'invite' });
    await new Promise(r => setTimeout(r, 50));
    signal({ type: 'offer', sdp: offer.sdp });
}

function createPeerConnection() {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    pc.onicecandidate = e => {
        if (e.candidate) signal({ type: 'ice', candidate: e.candidate.toJSON() });
    };

    pc.ontrack = e => {
        $('remote-video').srcObject = e.streams[0];
        $('call-status').textContent = 'Соединение установлено';
    };

    pc.onconnectionstatechange = () => {
        const state = pc.connectionState;
        console.log('RTCPeerConnection state:', state);
        if (state === 'connected') $('call-status').textContent = 'Разговор...';

        if (['disconnected', 'failed', 'closed'].includes(state) && !_isHangingUp) {
            hangup();
        }
    };

    return pc;
}

async function handleSignal(msg) {
    const S = window.AppState;
    const from = msg.from;

    if (msg.type === 'invite') {
        if ($('call-overlay').classList.contains('show')) return;
        _incomingCallFrom = from;
        showIncomingCallUI(msg.username || 'Собеседник', from);
        return;
    }

    if (msg.type === 'offer') {
        if (!S.pc) S.pc = createPeerConnection();
        await S.pc.setRemoteDescription({ type: 'offer', sdp: msg.sdp });

        const answer = await S.pc.createAnswer();
        await S.pc.setLocalDescription(answer);

        S._pendingAnswer = { sdp: answer.sdp, to: from };

        if (S._pendingCandidates?.length) {
            for (const c of S._pendingCandidates) {
                try { await S.pc.addIceCandidate(c); } catch {}
            }
            S._pendingCandidates = [];
        }
    }

    if (msg.type === 'answer') {
        if (S.pc?.signalingState !== 'stable') {
            await S.pc?.setRemoteDescription({ type: 'answer', sdp: msg.sdp });
        }
    }

    if (msg.type === 'ice') {
        try {
            if (S.pc?.remoteDescription) {
                await S.pc.addIceCandidate(msg.candidate);
            } else {
                if (!S._pendingCandidates) S._pendingCandidates = [];
                S._pendingCandidates.push(msg.candidate);
            }
        } catch (e) {
            console.warn('ICE error:', e.message);
        }
    }

    if (msg.type === 'bye') {
        hideIncomingCallUI();
        hangup();
    }
}

function showIncomingCallUI(callerName) {
    let banner = $('incoming-call-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'incoming-call-banner';
        banner.style.cssText = [
            'position:fixed', 'top:20px', 'left:50%', 'transform:translateX(-50%)',
            'background:#1a1a2e', 'border:2px solid #4ecdc4', 'border-radius:16px',
            'padding:20px 28px', 'z-index:9999', 'display:flex', 'align-items:center',
            'gap:16px', 'box-shadow:0 8px 32px rgba(0,0,0,.6)',
            'font-family:sans-serif', 'color:#e0e0e0'
        ].join(';');

        banner.innerHTML = `
            <div style="font-size:32px" id="call-ring-emoji">📞</div>
            <div>
                <div id="incoming-caller-name" style="font-weight:700;font-size:16px;margin-bottom:4px"></div>
                <div style="font-size:13px;color:#4ecdc4">Входящий звонок...</div>
            </div>
            <div style="display:flex;gap:10px;margin-left:12px">
                <button onclick="window.acceptCall()"
                    title="Принять"
                    style="background:#27ae60;color:#fff;border:none;border-radius:50%;
                           width:48px;height:48px;font-size:22px;cursor:pointer">✅</button>
                <button onclick="window.declineCall()"
                    title="Отклонить"
                    style="background:#e74c3c;color:#fff;border:none;border-radius:50%;
                           width:48px;height:48px;font-size:22px;cursor:pointer">❌</button>
            </div>`;

        if (!document.getElementById('webrtc-style')) {
            const style = document.createElement('style');
            style.id = 'webrtc-style';
            style.textContent = `
                @keyframes ring { 0%,100%{transform:rotate(-15deg)} 50%{transform:rotate(15deg)} }
                #call-ring-emoji { animation: ring .5s infinite; display:inline-block; }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(banner);
    }

    const nameEl = document.getElementById('incoming-caller-name');
    if (nameEl) nameEl.textContent = callerName + ' звонит';
    banner.style.display = 'flex';
}

function hideIncomingCallUI() {
    const banner = $('incoming-call-banner');
    if (banner) banner.style.display = 'none';
}

export async function acceptCall() {
    const S = window.AppState;
    hideIncomingCallUI();

    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        $('local-video').srcObject = S.localStream;
    } catch (e) {
        console.warn('Нет микрофона:', e.message);
    }

    if (S.pc && S.localStream) {
        S.localStream.getTracks().forEach(t => {
            try { S.pc.addTrack(t, S.localStream); } catch {}
        });
    }

    if (S._pendingCandidates?.length && S.pc?.remoteDescription) {
        for (const c of S._pendingCandidates) {
            try { await S.pc.addIceCandidate(c); } catch {}
        }
        S._pendingCandidates = [];
    }

    if (S._pendingAnswer) {
        signal({ type: 'answer', sdp: S._pendingAnswer.sdp, to: S._pendingAnswer.to });
        S._pendingAnswer = null;
    }

    $('call-peer-name').textContent = 'Собеседник';
    $('call-peer-avatar').textContent = '📞';
    $('call-status').textContent = 'Подключение...';
    $('call-overlay').classList.add('show');
    _isHangingUp = false;
}

export function declineCall() {
    const S = window.AppState;
    hideIncomingCallUI();
    signal({ type: 'bye', to: _incomingCallFrom });
    S._pendingAnswer = null;
    S._pendingCandidates = [];
    if (S.pc) { S.pc.close(); S.pc = null; }
    _incomingCallFrom = null;
}

export function hangup() {
    if (_isHangingUp) return;
    _isHangingUp = true;

    const S = window.AppState;

    signal({ type: 'bye' });

    if (S.pc) {
        S.pc.onconnectionstatechange = null;
        S.pc.onicecandidate = null;
        S.pc.ontrack = null;
        S.pc.close();
        S.pc = null;
    }

    S.localStream?.getTracks().forEach(t => t.stop());
    S.localStream = null;

    $('remote-video').srcObject = null;
    $('local-video').srcObject  = null;
    $('call-overlay').classList.remove('show');
    hideIncomingCallUI();

    S._pendingAnswer = null;
    S._pendingCandidates = [];
    _incomingCallFrom = null;

    $('mute-btn').textContent = '🎤';
    $('cam-btn').textContent  = '📷';
    S.isMuted  = false;
    S.isCamOff = false;

    setTimeout(() => { _isHangingUp = false; }, 500);
}

export function toggleMute() {
    const S = window.AppState;
    S.isMuted = !S.isMuted;
    S.localStream?.getAudioTracks().forEach(t => { t.enabled = !S.isMuted; });
    $('mute-btn').innerHTML = S.isMuted ? '<svg  xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24" > <path d="M8.03 12.27a3.98 3.98 0 0 0 3.7 3.7zM20 12h-2c0 1.29-.42 2.49-1.12 3.47l-1.44-1.44c.36-.59.56-1.28.56-2.02v-6c0-2.21-1.79-4-4-4s-4 1.79-4 4v.59L2.71 1.29 1.3 2.7l20 20 1.41-1.41-4.4-4.4A7.9 7.9 0 0 0 20 12M10 6c0-1.1.9-2 2-2s2 .9 2 2v6c0 .18-.03.35-.07.51L10 8.58V5.99Z"></path><path d="M12 18c-3.31 0-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c.74-.09 1.45-.29 2.12-.57l-1.57-1.57c-.49.13-1.01.21-1.55.21"></path></svg>' : '<svg  xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24" ><path d="M16 12V6c0-2.21-1.79-4-4-4S8 3.79 8 6v6c0 2.21 1.79 4 4 4s4-1.79 4-4m-6 0V6c0-1.1.9-2 2-2s2 .9 2 2v6c0 1.1-.9 2-2 2s-2-.9-2-2"></path><path d="M18 12c0 3.31-2.69 6-6 6s-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c3.94-.49 7-3.86 7-7.93z"></path>';

}

export function toggleCam() {
    const S = window.AppState;
    S.isCamOff = !S.isCamOff;
    S.localStream?.getVideoTracks().forEach(t => { t.enabled = !S.isCamOff; });
    $('cam-btn').innerHTML = S.isCamOff ? '<svg  xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24" ><path d="M4 18V8.24L2.12 6.36c-.07.2-.12.42-.12.64v11c0 1.1.9 2 2 2h11.76l-2-2zm18 0V7c0-1.1-.9-2-2-2h-2.59L14.7 2.29a1 1 0 0 0-.71-.29h-4c-.27 0-.52.11-.71.29L6.57 5H6.4L2.71 1.29 1.3 2.7l20 20 1.41-1.41-1.62-1.62c.55-.36.91-.97.91-1.67M10.41 4h3.17l2.71 2.71c.19.19.44.29.71.29h3v11h-.59l-3.99-3.99c.36-.59.57-1.28.57-2.01 0-2.17-1.83-4-4-4-.73 0-1.42.21-2.01.57L7.91 6.5zm1.08 6.08c.16-.05.33-.08.51-.08 1.07 0 2 .93 2 2 0 .17-.03.34-.08.51z"></path><path d="M8.03 12.27c.14 1.95 1.75 3.56 3.7 3.7z"></path></svg>' : '<svg  xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24" > <path d="M12 8c-2.17 0-4 1.83-4 4s1.83 4 4 4 4-1.83 4-4-1.83-4-4-4m0 6c-1.07 0-2-.93-2-2s.93-2 2-2 2 .93 2 2-.93 2-2 2"></path><path d="M20 5h-2.59L14.7 2.29a1 1 0 0 0-.71-.29h-4c-.27 0-.52.11-.71.29L6.57 5H3.98c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2Zm0 13H4V7h3c.27 0 .52-.11.71-.29L10.42 4h3.17l2.71 2.71c.19.19.44.29.71.29h3v11Z"></path></svg>';

}