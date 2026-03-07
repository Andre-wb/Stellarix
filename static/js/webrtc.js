// static/js/webrtc.js
// ============================================================================
// Модуль WebRTC для аудио/видеозвонков в комнате.
// Обрабатывает сигнализацию через WebSocket, создание peer-соединения,
// управление медиапотоками, интерфейс входящего вызова.
//
// Мониторинг качества звонка (RTT, jitter, потери пакетов) через getStats().
// Метрики обновляются каждые 2 секунды и отображаются в overlay звонка.
//
// Адаптивный контроль качества (критерий 3 — контроль перегрузки):
//   • При ухудшении сети (RTT>300мс, loss>5%) понижается bitrate видео / аудио
//   • При восстановлении сети bitrate возвращается к норме
//   • Алгоритм на основе конечного автомата: high → medium → low → audio_only
// ============================================================================

import { $ } from './utils.js';

// STUN-серверы для ICE
const ICE_SERVERS = [
    { urls: 'stun:stun.relay.metered.ca:80' },
    { urls: 'turn:global.relay.metered.ca:80',                username: '89d094ff4761a3765d7ab286', credential: 'bnMneF4zVHEBd3TG' },
    { urls: 'turn:global.relay.metered.ca:80?transport=tcp',  username: '89d094ff4761a3765d7ab286', credential: 'bnMneF4zVHEBd3TG' },
    { urls: 'turn:global.relay.metered.ca:443',               username: '89d094ff4761a3765d7ab286', credential: 'bnMneF4zVHEBd3TG' },
    { urls: 'turns:global.relay.metered.ca:443?transport=tcp',username: '89d094ff4761a3765d7ab286', credential: 'bnMneF4zVHEBd3TG' },
];

let _isHangingUp      = false;
let _incomingCallFrom = null;
let _statsInterval    = null;
let _prevStats        = null;

// ─── Пороги качества ──────────────────────────────────────────────────────────
const QUALITY = {
    GOOD: { rtt: 150,  loss: 2,  jitter: 30  },
    FAIR: { rtt: 300,  loss: 8,  jitter: 80  },
    // хуже → poor
};

// ─── Адаптивное управление bitrate ────────────────────────────────────────────
// Уровни качества видео (kbps)
const VIDEO_BITRATES = {
    high:       2500_000,    // 2.5 Mbps — отличное качество
    medium:      800_000,    // 800 kbps — среднее
    low:         200_000,    // 200 kbps — плохая сеть
    audio_only:        0,    // видео отключено
};

// Уровни качества аудио (bps)
const AUDIO_BITRATES = {
    high:    64_000,   // 64 kbps opus
    medium:  32_000,   // 32 kbps
    low:     16_000,   // 16 kbps
    audio_only: 24_000,
};

let _currentQualityLevel = 'high';   // текущий уровень
let _qualityStableCount  = 0;        // счётчик стабильных итераций (для повышения)

// Минимальное число итераций подряд с хорошей сетью прежде чем повысить качество
const QUALITY_UPGRADE_THRESHOLD = 5;

// ----------------------------------------------------------------------------
// Подключение к сигнальному WebSocket
// ----------------------------------------------------------------------------
export function connectSignal(roomId) {
    const S = window.AppState;

    if (S.signalWs?.readyState === WebSocket.OPEN && S._signalRoomId === roomId) return;

    if (S.signalWs) {
        S.signalWs.onclose = null;
        S.signalWs.close();
        S.signalWs = null;
    }

    S._signalRoomId = roomId;  // запоминаем правильный ID

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    S.signalWs  = new WebSocket(`${proto}://${location.host}/ws/signal/${roomId}`);

    S.signalWs.onopen = () => console.log('Signal WS открыт, комната', roomId);

    S.signalWs.onmessage = async e => {
        try { await handleSignal(JSON.parse(e.data)); }
        catch (err) { console.error('Signal msg error:', err); }
    };

    S.signalWs.onclose = e => {
        console.log('Signal WS закрыт, code=', e.code);
        S.signalWs = null;
        if (e.code !== 1000) {
            setTimeout(() => {
                if (S._signalRoomId === roomId && !S.signalWs) {
                    connectSignal(roomId);
                }
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

function _sdpHasVideo(sdp) {
    return typeof sdp === 'string' && /^m=video /m.test(sdp);
}

// ----------------------------------------------------------------------------
// Инициирование звонков
// ----------------------------------------------------------------------------
export async function startVoiceCall() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    console.log('currentRoom:', JSON.stringify(S.currentRoom));
    console.log('signalRoomId:', S.currentRoom.signalRoomId);
    console.log('id:', S.currentRoom.id);
    console.log('_signalRoomId:', S._signalRoomId);
    if (!S.signalWs || S.signalWs.readyState === WebSocket.CLOSED) {
        const signalId = S.currentRoom.signalRoomId ?? S.currentRoom.id;
        connectSignal(signalId);
    }
    try { await waitForSignalOpen(); }
    catch (e) { alert('Нет соединения с сигнальным сервером: ' + e.message); return; }

    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (e) { alert('Нет доступа к микрофону: ' + e.message); return; }

    _showCallOverlay({ name: S.currentRoom.name, avatar: '💬', status: 'Вызов...', hasVideo: false });
    _isHangingUp = false;
    _currentQualityLevel = 'high';
    _qualityStableCount  = 0;

    S.pc = createPeerConnection();
    S.localStream.getTracks().forEach(t => S.pc.addTrack(t, S.localStream));

    const offer = await S.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: false });
    await S.pc.setLocalDescription(offer);

    signal({ type: 'invite', hasVideo: false });
    await new Promise(r => setTimeout(r, 50));
    signal({ type: 'offer', sdp: offer.sdp });
}

export async function startVideoCall() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    if (!S.signalWs || S.signalWs.readyState === WebSocket.CLOSED) {
        const signalId = S.currentRoom.signalRoomId ?? S.currentRoom.id;
        connectSignal(signalId);
    }
    try { await waitForSignalOpen(); }
    catch (e) { alert('Нет соединения с сигнальным сервером: ' + e.message); return; }

    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    } catch (e) { alert('Нет доступа к камере/микрофону: ' + e.message); return; }

    _showCallOverlay({ name: S.currentRoom.name, avatar: '💬', status: 'Видеозвонок...', hasVideo: true });
    _isHangingUp = false;
    S.isCamOff   = false;
    _currentQualityLevel = 'high';
    _qualityStableCount  = 0;
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
// RTCPeerConnection
// ----------------------------------------------------------------------------
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

        if (state === 'connected') {
            $('call-status').textContent = 'Разговор...';
            _startStatsMonitor(pc);
        }
        if (state === 'disconnected') {
            _setQualityBadge('?', 'grey');
        }
        if (['failed', 'closed'].includes(state) && !_isHangingUp) {
            hangup();
        }
    };

    return pc;
}

// ============================================================================
// МОНИТОРИНГ И АДАПТИВНОЕ УПРАВЛЕНИЕ КАЧЕСТВОМ
// ============================================================================

function _startStatsMonitor(pc) {
    _stopStatsMonitor();
    _prevStats = null;
    _ensureQualityBadge();

    _statsInterval = setInterval(async () => {
        if (!pc || pc.connectionState !== 'connected') {
            _stopStatsMonitor();
            return;
        }
        try {
            const metrics = await _collectStats(pc);
            if (metrics) {
                _applyMetricsToUI(metrics);
                await _adaptQuality(pc, metrics);   // ← адаптивное управление
            }
        } catch (e) {
            console.debug('getStats error:', e);
        }
    }, 2000);
}

function _stopStatsMonitor() {
    if (_statsInterval) {
        clearInterval(_statsInterval);
        _statsInterval = null;
    }
    _prevStats = null;
}

async function _collectStats(pc) {
    const statsReport = await pc.getStats();
    const now         = Date.now();

    let rtt         = null;
    let jitter      = null;
    let packetsLost = null;
    let packetsRecv = null;
    let bytesRecv   = null;
    let transport   = null;

    statsReport.forEach(report => {
        if (report.type === 'candidate-pair' && report.state === 'succeeded') {
            if (report.currentRoundTripTime != null) {
                const candidate_rtt = report.currentRoundTripTime * 1000;
                if (rtt === null || candidate_rtt < rtt) rtt = candidate_rtt;
            }
        }
        if (report.type === 'inbound-rtp' && report.kind === 'audio') {
            if (report.jitter      != null) jitter      = report.jitter * 1000;
            if (report.packetsLost != null) packetsLost = report.packetsLost;
            if (report.packetsReceived != null) packetsRecv = report.packetsReceived;
            if (report.bytesReceived   != null) bytesRecv   = report.bytesReceived;
        }
        if (report.type === 'local-candidate' && report.candidateType) {
            const priority = { relay: 3, srflx: 2, host: 1 };
            const cur_p    = priority[report.candidateType] ?? 0;
            const prev_p   = priority[transport] ?? 0;
            if (cur_p > prev_p) transport = report.candidateType;
        }
    });

    let lossPercent = null;
    let bitrateKbps = null;

    if (_prevStats) {
        const dt = (now - _prevStats.ts) / 1000;
        if (packetsLost != null && _prevStats.packetsLost != null &&
            packetsRecv != null && _prevStats.packetsRecv != null) {
            const deltaLost  = Math.max(0, packetsLost - _prevStats.packetsLost);
            const deltaRecv  = Math.max(0, packetsRecv - _prevStats.packetsRecv);
            const deltaTotal = deltaLost + deltaRecv;
            lossPercent = deltaTotal > 0 ? (deltaLost / deltaTotal) * 100 : 0;
        }
        if (bytesRecv != null && _prevStats.bytesRecv != null && dt > 0) {
            const deltaBytes = Math.max(0, bytesRecv - _prevStats.bytesRecv);
            bitrateKbps = (deltaBytes * 8) / dt / 1000;
        }
    }

    _prevStats = { ts: now, packetsLost, packetsRecv, bytesRecv };

    if (rtt === null && jitter === null && lossPercent === null) return null;
    return { rtt, jitter, lossPercent, bitrateKbps, transport };
}

// ── Адаптивное управление качеством ──────────────────────────────────────────

/**
 * Конечный автомат адаптивного управления качеством.
 *
 * Логика:
 *   - Если сеть плохая (poor) → понижаем уровень на один шаг вниз
 *   - Если сеть справедливая (fair) → держим текущий уровень
 *   - Если сеть хорошая (good) N раз подряд → повышаем уровень на шаг
 *
 * Уровни (от высшего к низшему): high → medium → low → audio_only
 */
async function _adaptQuality(pc, metrics) {
    if (!pc) return;

    const { rtt, lossPercent, jitter } = metrics;

    // Определяем состояние сети
    let networkState = 'good';
    if (
        (rtt         != null && rtt         > QUALITY.FAIR.rtt)   ||
        (lossPercent != null && lossPercent > QUALITY.FAIR.loss)  ||
        (jitter      != null && jitter      > QUALITY.FAIR.jitter)
    ) networkState = 'poor';
    else if (
        (rtt         != null && rtt         > QUALITY.GOOD.rtt)   ||
        (lossPercent != null && lossPercent > QUALITY.GOOD.loss)  ||
        (jitter      != null && jitter      > QUALITY.GOOD.jitter)
    ) networkState = 'fair';

    const levels = ['audio_only', 'low', 'medium', 'high'];
    const curIdx = levels.indexOf(_currentQualityLevel);

    let newLevel = _currentQualityLevel;

    if (networkState === 'poor') {
        // Понижаем качество
        _qualityStableCount = 0;
        if (curIdx > 0) newLevel = levels[curIdx - 1];
    } else if (networkState === 'good') {
        // Считаем стабильные итерации
        _qualityStableCount++;
        if (_qualityStableCount >= QUALITY_UPGRADE_THRESHOLD && curIdx < levels.length - 1) {
            newLevel            = levels[curIdx + 1];
            _qualityStableCount = 0;
        }
    } else {
        // fair — ничего не меняем
        _qualityStableCount = 0;
    }

    if (newLevel !== _currentQualityLevel) {
        console.info(`[AdaptiveQuality] ${_currentQualityLevel} → ${newLevel} (net=${networkState})`);
        _currentQualityLevel = newLevel;
        await _applyQualityLevel(pc, newLevel);
    }
}

/**
 * Применяет уровень качества к RTCPeerConnection через setParameters().
 */
async function _applyQualityLevel(pc, level) {
    const senders = pc.getSenders();

    for (const sender of senders) {
        if (!sender.track) continue;
        try {
            const params = sender.getParameters();
            if (!params.encodings || params.encodings.length === 0) {
                params.encodings = [{}];
            }

            if (sender.track.kind === 'video') {
                if (level === 'audio_only') {
                    // Отключаем видео трек
                    sender.track.enabled = false;
                    params.encodings[0].maxBitrate = 0;
                } else {
                    sender.track.enabled = true;
                    params.encodings[0].maxBitrate = VIDEO_BITRATES[level];
                    // Для низкого качества ещё понижаем framerate
                    if (level === 'low')   params.encodings[0].maxFramerate = 15;
                    if (level === 'medium') params.encodings[0].maxFramerate = 24;
                    if (level === 'high')   delete params.encodings[0].maxFramerate;
                }
            } else if (sender.track.kind === 'audio') {
                const targetBitrate = AUDIO_BITRATES[level] ?? AUDIO_BITRATES.medium;
                params.encodings[0].maxBitrate = targetBitrate;
            }

            await sender.setParameters(params);
        } catch (e) {
            console.debug(`[AdaptiveQuality] setParameters failed for ${sender.track.kind}:`, e.message);
        }
    }

    // Обновляем UI
    const levelLabel = { high: '🟢 HD', medium: '🟡 SD', low: '🟠 Low', audio_only: '🔴 Audio' }[level];
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('sp-quality-level', levelLabel);

    // Показываем уведомление пользователю при деградации
    if (level !== 'high') {
        const statusEl = $('call-status');
        if (statusEl) {
            const prev = statusEl.textContent;
            statusEl.textContent = `Адаптация сети: ${levelLabel}`;
            setTimeout(() => { if (statusEl) statusEl.textContent = prev; }, 3000);
        }
    }
}

// ── Отображение метрик в UI ────────────────────────────────────────────────────

function _applyMetricsToUI(metrics) {
    const { rtt, jitter, lossPercent, bitrateKbps, transport } = metrics;

    let level = 'good';
    if (
        (rtt         != null && rtt         > QUALITY.FAIR.rtt)   ||
        (lossPercent != null && lossPercent > QUALITY.FAIR.loss)  ||
        (jitter      != null && jitter      > QUALITY.FAIR.jitter)
    ) level = 'poor';
    else if (
        (rtt         != null && rtt         > QUALITY.GOOD.rtt)   ||
        (lossPercent != null && lossPercent > QUALITY.GOOD.loss)  ||
        (jitter      != null && jitter      > QUALITY.GOOD.jitter)
    ) level = 'fair';

    const colors = { good: '#27ae60', fair: '#f39c12', poor: '#e74c3c' };
    const labels = { good: 'Хорошее', fair: 'Среднее', poor: 'Плохое' };

    const rttVal = document.getElementById('wrtc-rtt-val');
    const dot    = document.getElementById('wrtc-dot');
    if (rttVal) rttVal.textContent = rtt != null ? `${rtt.toFixed(0)} мс` : '—';
    if (dot)    dot.style.background = colors[level];

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('sp-rtt',    rtt         != null ? `${rtt.toFixed(0)} мс`           : '—');
    set('sp-jitter', jitter      != null ? `${jitter.toFixed(0)} мс`        : '—');
    set('sp-loss',   lossPercent != null ? `${lossPercent.toFixed(1)} %`    : '—');
    set('sp-brate',  bitrateKbps != null ? `${bitrateKbps.toFixed(0)} kbps` : '—');
    set('sp-type',   transport ? _transportLabel(transport) : '—');
    set('sp-qual',   labels[level]);

    const qualEl = document.getElementById('sp-qual');
    if (qualEl) qualEl.style.color = colors[level];

    const upd = document.getElementById('sp-updated');
    if (upd) upd.textContent = `обновлено: ${new Date().toLocaleTimeString()}`;

    console.debug('[WebRTC Stats]',
        `RTT=${rtt?.toFixed(0)}мс jitter=${jitter?.toFixed(0)}мс ` +
        `loss=${lossPercent?.toFixed(1)}% brate=${bitrateKbps?.toFixed(0)}kbps [${transport}] ` +
        `quality=${_currentQualityLevel}`);
}

function _transportLabel(t) {
    return { host: 'Прямое (LAN)', srflx: 'NAT (STUN)', relay: 'Relay (TURN)' }[t] ?? t;
}

// ── DOM: элементы overlay + статистика ────────────────────────────────────────

function _ensureQualityBadge() {
    if ($('wrtc-rtt-badge')) return;

    const overlay = $('call-overlay');
    if (!overlay) return;

    // RTT inline badge
    const rttBadge = document.createElement('div');
    rttBadge.id = 'wrtc-rtt-badge';
    rttBadge.style.cssText = [
        'display:inline-flex', 'align-items:center', 'gap:5px',
        'margin-top:6px', 'font-size:13px', 'font-weight:600',
        'color:#bbb', 'min-height:18px',
    ].join(';');
    rttBadge.innerHTML =
        '<span id="wrtc-dot" style="width:8px;height:8px;border-radius:50%;' +
        'background:#555;flex-shrink:0;transition:background .3s"></span>' +
        '<span style="color:#888;font-weight:400">Задержка:</span>' +
        '<span id="wrtc-rtt-val" style="font-variant-numeric:tabular-nums">—</span>';

    const statusEl = $('call-status');
    if (statusEl?.parentNode) statusEl.parentNode.insertBefore(rttBadge, statusEl.nextSibling);
    else overlay.appendChild(rttBadge);

    // ⚙ кнопка
    const gearBtn = document.createElement('button');
    gearBtn.id    = 'wrtc-gear-btn';
    gearBtn.title = 'Статистика соединения';
    gearBtn.innerHTML =
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">' +
        '<path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58' +
        'c0.18-0.14,0.23-0.41,0.12-0.61l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96' +
        'c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41h-3.84' +
        'c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33' +
        'c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58' +
        'C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58c-0.18,0.14-0.23,0.41-0.12,0.61' +
        'l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54' +
        'c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54' +
        'c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32' +
        'c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z' +
        'M12,15.6c-1.98,0-3.6-1.62-3.6-3.6s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/>' +
        '</svg>';
    gearBtn.style.cssText = [
        'position:absolute', 'top:12px', 'right:14px',
        'background:rgba(255,255,255,.08)', 'border:none',
        'border-radius:50%', 'width:32px', 'height:32px',
        'cursor:pointer', 'color:#aaa',
        'display:flex', 'align-items:center', 'justify-content:center',
        'transition:background .2s,color .2s', 'z-index:10',
    ].join(';');
    gearBtn.onmouseenter = () => { gearBtn.style.background='rgba(255,255,255,.18)'; gearBtn.style.color='#fff'; };
    gearBtn.onmouseleave = () => { gearBtn.style.background='rgba(255,255,255,.08)'; gearBtn.style.color='#aaa'; };
    gearBtn.onclick = _toggleStatsPanel;
    overlay.appendChild(gearBtn);

    // Панель статистики
    const panel = document.createElement('div');
    panel.id = 'wrtc-stats-panel';
    panel.style.cssText = [
        'position:absolute', 'top:50px', 'right:14px',
        'background:rgba(8,8,18,.93)',
        'backdrop-filter:blur(14px)', '-webkit-backdrop-filter:blur(14px)',
        'border:1px solid rgba(255,255,255,.1)',
        'border-radius:12px', 'padding:14px 18px 12px',
        'min-width:260px', 'font-size:12px', 'line-height:2.0',
        'color:#ddd', 'display:none', 'z-index:20',
        'box-shadow:0 8px 32px rgba(0,0,0,.6)',
    ].join(';');
    panel.innerHTML =
        '<div style="font-size:13px;font-weight:700;margin-bottom:10px;' +
        'color:#fff;display:flex;align-items:center;gap:7px">' +
        '📊 <span>Статистика соединения</span></div>' +
        '<table style="border-collapse:collapse;width:100%">' +
        '<tr><td style="color:#666;padding-right:14px;white-space:nowrap">Задержка (RTT)</td>' +
        '<td id="sp-rtt"           style="font-weight:700;text-align:right;font-variant-numeric:tabular-nums">—</td></tr>' +
        '<tr><td style="color:#666">Джиттер</td>' +
        '<td id="sp-jitter"        style="font-weight:700;text-align:right;font-variant-numeric:tabular-nums">—</td></tr>' +
        '<tr><td style="color:#666">Потери пакетов</td>' +
        '<td id="sp-loss"          style="font-weight:700;text-align:right;font-variant-numeric:tabular-nums">—</td></tr>' +
        '<tr><td style="color:#666">Входящий поток</td>' +
        '<td id="sp-brate"         style="font-weight:700;text-align:right;font-variant-numeric:tabular-nums">—</td></tr>' +
        '<tr><td style="color:#666">Тип соединения</td>' +
        '<td id="sp-type"          style="font-weight:700;text-align:right">—</td></tr>' +
        '<tr><td style="color:#666">Качество сети</td>' +
        '<td id="sp-qual"          style="font-weight:700;text-align:right">—</td></tr>' +
        '<tr><td style="color:#666">Уровень видео</td>' +
        '<td id="sp-quality-level" style="font-weight:700;text-align:right">—</td></tr>' +
        '</table>' +
        '<div id="sp-updated" style="margin-top:10px;padding-top:8px;' +
        'border-top:1px solid rgba(255,255,255,.07);' +
        'font-size:10px;color:#444;text-align:right">ожидание данных...</div>';
    overlay.appendChild(panel);

    document.addEventListener('click', e => {
        const p = $('wrtc-stats-panel');
        const g = $('wrtc-gear-btn');
        if (p && g && !p.contains(e.target) && !g.contains(e.target))
            p.style.display = 'none';
    });

    if (!document.getElementById('wrtc-style')) {
        const s = document.createElement('style');
        s.id = 'wrtc-style';
        s.textContent =
            '#wrtc-stats-panel{animation:wrtc-fade .15s ease}' +
            '@keyframes wrtc-fade{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}' +
            '@keyframes ring{0%,100%{transform:rotate(-15deg)}50%{transform:rotate(15deg)}}' +
            '#call-ring-emoji{animation:ring .5s infinite;display:inline-block}';
        document.head.appendChild(s);
    }
}

function _toggleStatsPanel() {
    const p = $('wrtc-stats-panel');
    if (!p) return;
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
}

function _setQualityBadge(icon, color) {
    const dot = document.getElementById('wrtc-dot');
    if (dot) dot.style.background = color;
}

// ----------------------------------------------------------------------------
// Обработка сигнальных сообщений
// ----------------------------------------------------------------------------
async function handleSignal(msg) {
    const S = window.AppState;
    const from = msg.from;

    if (msg.type === 'invite') {
        if ($('call-overlay').classList.contains('show')) return;
        _incomingCallFrom = from;
        S._offerHasVideo  = !!msg.hasVideo;
        showIncomingCallUI(msg.username || 'Собеседник');
        return;
    }

    if (msg.type === 'offer') {
        if (!S.pc) S.pc = createPeerConnection();
        S._offerHasVideo = S._offerHasVideo ?? _sdpHasVideo(msg.sdp);
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
        } catch (e) { console.warn('ICE error:', e.message); }
    }

    if (msg.type === 'bye') {
        hideIncomingCallUI();
        hangup();
    }
}

// ----------------------------------------------------------------------------
// UI
// ----------------------------------------------------------------------------
function _showCallOverlay({ name, avatar, status, hasVideo }) {
    const overlay = $('call-overlay');
    if (!overlay) { console.error('call-overlay не найден в DOM'); return; }

    _ensureQualityBadge();

    const peerName   = $('call-peer-name');
    const peerAvatar = $('call-peer-avatar');
    const callStatus = $('call-status');
    const localVideo = $('local-video');

    if (peerName)   peerName.textContent   = name;
    if (peerAvatar) peerAvatar.textContent = avatar;
    if (callStatus) callStatus.textContent = status;
    if (localVideo) localVideo.srcObject   = window.AppState.localStream ?? null;

    overlay.classList.add('show');
    _setQualityBadge('⚙', '#888');
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
            style.textContent =
                '@keyframes ring { 0%,100%{transform:rotate(-15deg)} 50%{transform:rotate(15deg)} }' +
                '#call-ring-emoji { animation: ring .5s infinite; display:inline-block; }';
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

function hideIncomingCallUI() {
    const banner = $('incoming-call-banner');
    if (banner) banner.style.display = 'none';
}

// ----------------------------------------------------------------------------
// Принять / отклонить / завершить
// ----------------------------------------------------------------------------
export async function acceptCall() {
    const S = window.AppState;
    hideIncomingCallUI();
    const needVideo = !!S._offerHasVideo;
    try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: needVideo });
        $('local-video').srcObject = S.localStream;
    } catch (e) {
        if (needVideo) {
            try {
                S.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
                $('local-video').srcObject = S.localStream;
            } catch (e2) { console.warn('Нет микрофона:', e2.message); }
        } else { console.warn('Нет микрофона:', e.message); }
    }
    if (S.pc && S.localStream) {
        S.localStream.getTracks().forEach(t => {
            try { S.pc.addTrack(t, S.localStream); } catch {}
        });
    }
    const to = S._pendingOfferFrom;
    if (S.pc?.signalingState === 'have-remote-offer') {
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

    S.isCamOff           = !needVideo;
    _currentQualityLevel = 'high';
    _qualityStableCount  = 0;
    _updateCamBtn(S.isCamOff);

    _showCallOverlay({
        name:     'Собеседник',
        avatar:   needVideo ? '📹' : '📞',
        status:   'Подключение...',
        hasVideo: needVideo,
    });
    _isHangingUp = false;
}

export function declineCall() {
    const S = window.AppState;
    hideIncomingCallUI();
    signal({ type: 'bye', to: _incomingCallFrom });
    S._pendingAnswer     = null;
    S._pendingCandidates = [];
    S._offerHasVideo     = null;
    S._pendingOfferFrom  = null;
    if (S.pc) {
        S.pc.onconnectionstatechange = null;
        S.pc.onicecandidate          = null;
        S.pc.ontrack                 = null;
        S.pc.close();
        S.pc = null;
    }
    _incomingCallFrom    = null;
    _currentQualityLevel = 'high';
    _stopStatsMonitor();
}

export function hangup() {
    if (_isHangingUp) return;
    _isHangingUp = true;

    const S = window.AppState;
    signal({ type: 'bye' });
    _stopStatsMonitor();

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

    const detailEl = $('call-quality-detail');
    if (detailEl) detailEl.textContent = '';

    S._pendingAnswer     = null;
    S._pendingCandidates = [];
    S._offerHasVideo     = null;
    S._pendingOfferFrom  = null;
    _incomingCallFrom    = null;
    S.isMuted            = false;
    S.isCamOff           = false;
    _currentQualityLevel = 'high';
    _qualityStableCount  = 0;
    _updateMuteBtn(false);
    _updateCamBtn(false);

    setTimeout(() => { _isHangingUp = false; }, 500);
}

// ----------------------------------------------------------------------------
// Управление медиа-треками
// ----------------------------------------------------------------------------
export function toggleMute() {
    const S = window.AppState;
    S.isMuted = !S.isMuted;
    S.localStream?.getAudioTracks().forEach(t => { t.enabled = !S.isMuted; });
    _updateMuteBtn(S.isMuted);
}

export async function toggleCam() {
    const S = window.AppState;
    const existingVideoTracks = S.localStream?.getVideoTracks() ?? [];

    if (existingVideoTracks.length > 0) {
        S.isCamOff = !S.isCamOff;
        existingVideoTracks.forEach(t => { t.enabled = !S.isCamOff; });
        _updateCamBtn(S.isCamOff);
        return;
    }
    if (!S.pc) { console.warn('toggleCam: нет RTCPeerConnection'); return; }

    try {
        const videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
        const videoTrack  = videoStream.getVideoTracks()[0];

        if (S.localStream) S.localStream.addTrack(videoTrack);
        else S.localStream = videoStream;

        $('local-video').srcObject = S.localStream;
        S.pc.addTrack(videoTrack, S.localStream);
        S.isCamOff = false;
        _updateCamBtn(false);

        const offer = await S.pc.createOffer();
        await S.pc.setLocalDescription(offer);
        signal({ type: 'offer', sdp: offer.sdp });
    } catch (e) { alert('Не удалось включить камеру: ' + e.message); }
}

// ----------------------------------------------------------------------------
// Кнопки
// ----------------------------------------------------------------------------
function _updateMuteBtn(muted) {
    $('mute-btn').innerHTML = muted
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M8.03 12.27a3.98 3.98 0 0 0 3.7 3.7zM20 12h-2c0 1.29-.42 2.49-1.12 3.47l-1.44-1.44c.36-.59.56-1.28.56-2.02v-6c0-2.21-1.79-4-4-4s-4 1.79-4 4v.59L2.71 1.29 1.3 2.7l20 20 1.41-1.41-4.4-4.4A7.9 7.9 0 0 0 20 12M10 6c0-1.1.9-2 2-2s2 .9 2 2v6c0 .18-.03.35-.07.51L10 8.58V5.99Z"></path><path d="M12 18c-3.31 0-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c.74-.09 1.45-.29 2.12-.57l-1.57-1.57c-.49.13-1.01.21-1.55.21"></path></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M16 12V6c0-2.21-1.79-4-4-4S8 3.79 8 6v6c0 2.21 1.79 4 4 4s4-1.79 4-4m-6 0V6c0-1.1.9-2 2-2s2 .9 2 2v6c0 1.1-.9 2-2 2s-2-.9-2-2"></path><path d="M18 12c0 3.31-2.69 6-6 6s-6-2.69-6-6H4c0 4.07 3.06 7.44 7 7.93V22h2v-2.07c3.94-.49 7-3.86 7-7.93z"></path></svg>';
}

function _updateCamBtn(camOff) {
    $('cam-btn').innerHTML = camOff
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M4 18V8.24L2.12 6.36c-.07.2-.12.42-.12.64v11c0 1.1.9 2 2 2h11.76l-2-2zm18 0V7c0-1.1-.9-2-2-2h-2.59L14.7 2.29a1 1 0 0 0-.71-.29h-4c-.27 0-.52.11-.71.29L6.57 5H6.4L2.71 1.29 1.3 2.7l20 20 1.41-1.41-1.62-1.62c.55-.36.91-.97.91-1.67M10.41 4h3.17l2.71 2.71c.19.19.44.29.71.29h3v11h-.59l-3.99-3.99c.36-.59.57-1.28.57-2.01 0-2.17-1.83-4-4-4-.73 0-1.42.21-2.01.57L7.91 6.5zm1.08 6.08c.16-.05.33-.08.51-.08 1.07 0 2 .93 2 2 0 .17-.03.34-.08.51z"></path><path d="M8.03 12.27c.14 1.95 1.75 3.56 3.7 3.7z"></path></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" viewBox="0 0 24 24"><path d="M12 8c-2.17 0-4 1.83-4 4s1.83 4 4 4 4-1.83 4-4-1.83-4-4-4m0 6c-1.07 0-2-.93-2-2s.93-2 2-2 2 .93 2 2-.93 2-2 2"></path><path d="M20 5h-2.59L14.7 2.29a1 1 0 0 0-.71-.29h-4c-.27 0-.52.11-.71.29L6.57 5H3.98c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2Zm0 13H4V7h3c.27 0 .52-.11.71-.29L10.42 4h3.17l2.71 2.71c.19.19.44.29.71.29h3v11Z"></path></svg>';
}

// Экспортируем текущий уровень качества для внешнего использования
export function getCurrentQualityLevel() { return _currentQualityLevel; }