// static/js/webrtc.js
// ============================================================================
// Модуль WebRTC для аудио/видеозвонков в комнате.
// Обрабатывает сигнализацию через WebSocket, создание peer-соединения,
// управление медиапотоками, интерфейс входящего вызова.
// ============================================================================

import { $ } from './utils.js';

// STUN-серверы для ICE
const ICE_SERVERS = [{ urls: 'stun:stun.l.google.com:19302' }];

let _isHangingUp = false;          // флаг для предотвращения повторного завершения
let _incomingCallFrom = null;      // от кого пришёл входящий вызов

// ----------------------------------------------------------------------------
// Подключение к сигнальному WebSocket
// ----------------------------------------------------------------------------
/**
 * Устанавливает соединение с сигнальным WebSocket для указанной комнаты.
 * @param {string} roomId - ID комнаты
 */
export function connectSignal(roomId) {
    const S = window.AppState;

    // Закрываем предыдущее соединение, если есть
    if (S.signalWs) {
        S.signalWs.onclose = null;
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
        // Если комната ещё активна и закрытие не штатное, пробуем переподключиться
        if (S.currentRoom?.id === roomId && e.code !== 1000) {
            setTimeout(() => {
                if (S.currentRoom?.id === roomId && !S.signalWs) connectSignal(roomId);
            }, 3000);
        }
    };

    S.signalWs.onerror = err => console.error('Signal WS error:', err);
}

/**
 * Ожидает, пока сигнальный WebSocket перейдёт в состояние OPEN.
 * @param {number} timeout - таймаут в мс
 * @returns {Promise<void>}
 */
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

/**
 * Отправляет сообщение через сигнальный WebSocket.
 * @param {Object} msg - сообщение (будет преобразовано в JSON)
 */
function signal(msg) {
    const S = window.AppState;
    if (S.signalWs?.readyState === WebSocket.OPEN) {
        S.signalWs.send(JSON.stringify(msg));
    } else {
        console.warn('signal(): WS не готов, тип=', msg.type);
    }
}

/**
 * Проверяет, содержит ли SDP видео-дорожку.
 * @param {string} sdp - SDP offer/answer
 * @returns {boolean}
 */
function _sdpHasVideo(sdp) {
    return typeof sdp === 'string' && /^m=video /m.test(sdp);
}

// ----------------------------------------------------------------------------
// Инициирование звонков
// ----------------------------------------------------------------------------
/**
 * Начинает голосовой вызов (только аудио).
 */
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

    // Отображаем интерфейс звонка
    $('call-peer-name').textContent   = S.currentRoom.name;
    $('call-peer-avatar').textContent = '💬';
    $('call-status').textContent      = 'Вызов...';
    $('local-video').srcObject        = S.localStream;
    $('call-overlay').classList.add('show');
    _isHangingUp = false;

    S.pc = createPeerConnection();
    S.localStream.getTracks().forEach(t => S.pc.addTrack(t, S.localStream));

    const offer = await S.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: false });
    await S.pc.setLocalDescription(offer);

    signal({ type: 'invite', hasVideo: false });
    await new Promise(r => setTimeout(r, 50)); // небольшая задержка для гарантии доставки
    signal({ type: 'offer', sdp: offer.sdp });
}

/**
 * Начинает видеозвонок (аудио + видео).
 */
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

    $('call-peer-name').textContent   = S.currentRoom.name;
    $('call-peer-avatar').textContent = '💬';
    $('call-status').textContent      = 'Видеозвонок...';
    $('local-video').srcObject        = S.localStream;
    $('call-overlay').classList.add('show');
    _isHangingUp = false;
    S.isCamOff = false;
    _updateCamBtn(false);

    S.pc = createPeerConnection();
    S.localStream.getTracks().forEach(t => S.pc.addTrack(t, S.localStream));

    const offer = await S.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
    await S.pc.setLocalDescription(offer);

    signal({ type: 'invite', hasVideo: true });
    await new Promise(r => setTimeout(r, 50));
    signal({ type: 'offer', sdp: offer.sdp });
}

// ----------------------------------------------------------------------------
// Создание RTCPeerConnection
// ----------------------------------------------------------------------------
/**
 * Создаёт и настраивает RTCPeerConnection.
 * @returns {RTCPeerConnection}
 */
function createPeerConnection() {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    pc.onicecandidate = e => {
        if (e.candidate) signal({ type: 'ice', candidate: e.candidate.toJSON() });
    };

    pc.ontrack = e => {
        console.log('ontrack:', e.track.kind, e.streams[0]);
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

// ----------------------------------------------------------------------------
// Обработка сигнальных сообщений
// ----------------------------------------------------------------------------
/**
 * Обрабатывает входящее сигнальное сообщение.
 * @param {Object} msg - сообщение от сигнального сервера
 */
async function handleSignal(msg) {
    const S = window.AppState;
    const from = msg.from;

    if (msg.type === 'invite') {
        // Входящий вызов
        if ($('call-overlay').classList.contains('show')) return;
        _incomingCallFrom = from;
        S._offerHasVideo = !!msg.hasVideo;
        showIncomingCallUI(msg.username || 'Собеседник');
        return;
    }

    if (msg.type === 'offer') {
        if (!S.pc) S.pc = createPeerConnection();

        S._offerHasVideo = S._offerHasVideo ?? _sdpHasVideo(msg.sdp)
        await S.pc.setRemoteDescription({ type: 'offer', sdp: msg.sdp });
        S._pendingOfferFrom = from;
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

// ----------------------------------------------------------------------------
// Интерфейс входящего вызова
// ----------------------------------------------------------------------------
/**
 * Показывает баннер входящего вызова.
 * @param {string} callerName - имя звонящего
 */
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
                <div style="font-size:13px;color:#4ecdc4" id="incoming-call-type">Входящий звонок...</div>
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
    const typeEl = document.getElementById('incoming-call-type');
    if (nameEl) nameEl.textContent = callerName + ' звонит';
    if (typeEl) typeEl.textContent = window.AppState._offerHasVideo
        ? '📹 Входящий видеозвонок...'
        : '📞 Входящий звонок...';
    banner.style.display = 'flex';
}

/**
 * Скрывает баннер входящего вызова.
 */
function hideIncomingCallUI() {
    const banner = $('incoming-call-banner');
    if (banner) banner.style.display = 'none';
}

// ----------------------------------------------------------------------------
// Действия с вызовом (принять, отклонить, завершить)
// ----------------------------------------------------------------------------
/**
 * Принимает входящий вызов.
 */
export async function acceptCall() {
    const S = window.AppState;
    hideIncomingCallUI();
    const needVideo = !!S._offerHasVideo;
    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: needVideo,
        });
        $('local-video').srcObject = S.localStream;
    } catch (e) {
        if (needVideo) {
            console.warn('Нет камеры, пробуем только аудио:', e.message);
            try {
                S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
                $('local-video').srcObject = S.localStream;
            } catch (e2) {
                console.warn('Нет микрофона:', e2.message);
            }
        } else {
            console.warn('Нет микрофона:', e.message);
        }
    }
    if (S.pc && S.localStream) {
        S.localStream.getTracks().forEach(t => {
            try { S.pc.addTrack(t, S.localStream); } catch {}
        });
    }
    const to = S._pendingOfferFrom;
    if (S.pc && S.pc.signalingState === 'have-remote-offer') {
        const answer = await S.pc.createAnswer();
        await S.pc.setLocalDescription(answer);
        signal({ type: 'answer', sdp: answer.sdp, to });
    }
    S._pendingOfferFrom = null;
    if (S._pendingCandidates?.length) {
        for (const c of S._pendingCandidates) {
            try { await S.pc.addIceCandidate(c); } catch {}
        }
        S._pendingCandidates = [];
    }

    S.isCamOff = !needVideo;
    _updateCamBtn(S.isCamOff);

    $('call-peer-name').textContent   = 'Собеседник';
    $('call-peer-avatar').textContent = needVideo ? '📹' : '📞';
    $('call-status').textContent      = 'Подключение...';
    $('call-overlay').classList.add('show');
    _isHangingUp = false;
}

/**
 * Отклоняет входящий вызов.
 */
export function declineCall() {
    const S = window.AppState;
    hideIncomingCallUI();
    signal({ type: 'bye', to: _incomingCallFrom });
    S._pendingAnswer     = null;
    S._pendingCandidates = [];
    S._offerHasVideo     = null;
    S._pendingOfferFrom  = null;
    if (S.pc) { S.pc.close(); S.pc = null; }
    _incomingCallFrom = null;
}

/**
 * Завершает текущий вызов.
 */
export function hangup() {
    if (_isHangingUp) return;
    _isHangingUp = true;

    const S = window.AppState;

    signal({ type: 'bye' });

    if (S.pc) {
        S.pc.onconnectionstatechange = null;
        S.pc.onicecandidate          = null;
        S.pc.ontrack                 = null;
        S.pc.close();
        S.pc = null;
    }

    S.localStream?.getTracks().forEach(t => t.stop());
    S.localStream = null;

    $('remote-video').srcObject = null;
    $('local-video').srcObject  = null;
    $('call-overlay').classList.remove('show');
    hideIncomingCallUI();

    S._pendingAnswer     = null;
    S._pendingCandidates = [];
    S._offerHasVideo     = null;
    S._pendingOfferFrom  = null;
    _incomingCallFrom    = null;

    S.isMuted  = false;
    S.isCamOff = false;
    _updateMuteBtn(false);
    _updateCamBtn(false);

    setTimeout(() => { _isHangingUp = false; }, 500);
}

// ----------------------------------------------------------------------------
// Управление медиа-треками во время звонка
// ----------------------------------------------------------------------------
/**
 * Переключает состояние микрофона (вкл/выкл).
 */
export function toggleMute() {
    const S = window.AppState;
    S.isMuted = !S.isMuted;
    S.localStream?.getAudioTracks().forEach(t => { t.enabled = !S.isMuted; });
    _updateMuteBtn(S.isMuted);
}

/**
 * Переключает состояние камеры (вкл/выкл). Если камера ещё не была добавлена,
 * пытается её включить и добавить в поток.
 */
export async function toggleCam() {
    const S = window.AppState;
    const existingVideoTracks = S.localStream?.getVideoTracks() ?? [];

    if (existingVideoTracks.length > 0) {
        S.isCamOff = !S.isCamOff;
        existingVideoTracks.forEach(t => { t.enabled = !S.isCamOff; });
        _updateCamBtn(S.isCamOff);
        return;
    }

    if (!S.pc) {
        console.warn('toggleCam: нет RTCPeerConnection');
        return;
    }

    try {
        const videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
        const videoTrack  = videoStream.getVideoTracks()[0];

        if (S.localStream) {
            S.localStream.addTrack(videoTrack);
        } else {
            S.localStream = videoStream;
        }
        $('local-video').srcObject = S.localStream;

        S.pc.addTrack(videoTrack, S.localStream);

        S.isCamOff = false;
        _updateCamBtn(false);

        // Отправляем обновлённый offer с новым видео-треком
        const offer = await S.pc.createOffer();
        await S.pc.setLocalDescription(offer);
        signal({ type: 'offer', sdp: offer.sdp });

    } catch (e) {
        alert('Не удалось включить камеру: ' + e.message);
    }
}

// ----------------------------------------------------------------------------
// Обновление иконок кнопок
// ----------------------------------------------------------------------------
/**
 * Обновляет внешний вид кнопки микрофона.
 * @param {boolean} muted - микрофон выключен?
 */
function _updateMuteBtn(muted) {
    $('mute-btn').innerHTML = muted
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M8.03 12.27a3.98 3.98 0 0 0 3.7 3.7zM20 12h-2c0 1.29-.42 2.49-1.12 3.47l-1.44-1.44c.36-.59.56-1.28.56-2.02v-6c0-2.21-1.79-4-4-4s-4 1.79-4 4v.59L2.71 1.29 1.3 2.7l20 20 1.41-1.41-4.4-4.4A7.9 7.9 0 0 0 20 12M10 6c0-1.1.9-2 2-2s2 .9 2 2v6c0 .18-.03.35-.07.51L10 8.58V5.99Z"></path><path d="M12 18c-3.31 0-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c.74-.09 1.45-.29 2.12-.57l-1.57-1.57c-.49.13-1.01.21-1.55.21"></path></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M16 12V6c0-2.21-1.79-4-4-4S8 3.79 8 6v6c0 2.21 1.79 4 4 4s4-1.79 4-4m-6 0V6c0-1.1.9-2 2-2s2 .9 2 2v6c0 1.1-.9 2-2 2s-2-.9-2-2"></path><path d="M18 12c0 3.31-2.69 6-6 6s-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c3.94-.49 7-3.86 7-7.93z"></path></svg>';
}

/**
 * Обновляет внешний вид кнопки камеры.
 * @param {boolean} camOff - камера выключена?
 */
function _updateCamBtn(camOff) {
    $('cam-btn').innerHTML = camOff
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M4 18V8.24L2.12 6.36c-.07.2-.12.42-.12.64v11c0 1.1.9 2 2 2h11.76l-2-2zm18 0V7c0-1.1-.9-2-2-2h-2.59L14.7 2.29a1 1 0 0 0-.71-.29h-4c-.27 0-.52.11-.71.29L6.57 5H6.4L2.71 1.29 1.3 2.7l20 20 1.41-1.41-1.62-1.62c.55-.36.91-.97.91-1.67M10.41 4h3.17l2.71 2.71c.19.19.44.29.71.29h3v11h-.59l-3.99-3.99c.36-.59.57-1.28.57-2.01 0-2.17-1.83-4-4-4-.73 0-1.42.21-2.01.57L7.91 6.5zm1.08 6.08c.16-.05.33-.08.51-.08 1.07 0 2 .93 2 2 0 .17-.03.34-.08.51z"></path><path d="M8.03 12.27c.14 1.95 1.75 3.56 3.7 3.7z"></path></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M12 8c-2.17 0-4 1.83-4 4s1.83 4 4 4 4-1.83 4-4-1.83-4-4-4m0 6c-1.07 0-2-.93-2-2s.93-2 2-2 2 .93 2 2-.93 2-2 2"></path><path d="M20 5h-2.59L14.7 2.29a1 1 0 0 0-.71-.29h-4c-.27 0-.52.11-.71.29L6.57 5H3.98c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2Zm0 13H4V7h3c.27 0 .52-.11.71-.29L10.42 4h3.17l2.71 2.71c.19.19.44.29.71.29h3v11Z"></path></svg>';
}