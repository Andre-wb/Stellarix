// static/js/voice_recorder.js
// ============================================================================
// Модуль записи голосовых сообщений.
// Позволяет записывать аудио с микрофона, отображать живую волну,
// предварительно прослушивать запись, визуализировать громкость (пики)
// и отправлять готовый файл на сервер.
// ============================================================================

let _mediaRecorder = null;
let _chunks        = [];
let _startTime     = 0;
let _timerInterval = null;
let _stream        = null;
let _animFrame     = null;
let _analyser      = null;
let _peaks         = [];
let _peakInterval  = null;
const VOICE_BTN_ID = 'voice-record-btn';

const SVG_PLAY  = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><path d="M15.5 12L10 15.5V8.5L15.5 12Z" fill="currentColor"/></svg>`;
const SVG_PAUSE = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><rect x="9" y="8" width="2.2" height="8" rx="1" fill="currentColor"/><rect x="12.8" y="8" width="2.2" height="8" rx="1" fill="currentColor"/></svg>`;

export function initVoiceRecorder() {
    document.addEventListener('click', e => {
        if (e.target.closest(`#${VOICE_BTN_ID}`)) toggleVoiceRecording();
    });
}

export async function toggleVoiceRecording() {
    if (_mediaRecorder?.state === 'recording') _stopRecording();
    else await _startRecording();
}

async function _startRecording() {
    try {
        _stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
        alert('Нет доступа к микрофону');
        return;
    }

    const actx = new AudioContext();
    const src  = actx.createMediaStreamSource(_stream);
    _analyser  = actx.createAnalyser();
    _analyser.fftSize = 256;
    src.connect(_analyser);

    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
            ? 'audio/ogg;codecs=opus' : 'audio/webm';

    _mediaRecorder = new MediaRecorder(_stream, { mimeType: mime });
    _chunks = []; _peaks = []; _startTime = Date.now();

    _mediaRecorder.ondataavailable = e => { if (e.data.size > 0) _chunks.push(e.data); };
    _mediaRecorder.onstop = _onStop;
    _mediaRecorder.start(100);

    _swapInputTo('record');
    _startTimer();
    _startPeaks();
    requestAnimationFrame(() => _drawLiveWave());

    document.getElementById(VOICE_BTN_ID)?.classList.add('recording');
}

function _stopRecording() {
    if (_mediaRecorder?.state === 'recording') _mediaRecorder.stop();
    _stream?.getTracks().forEach(t => t.stop());
    _stream = null;
    clearInterval(_timerInterval);
    clearInterval(_peakInterval);
    cancelAnimationFrame(_animFrame);
    _animFrame = null;
    _analyser  = null;
    document.getElementById(VOICE_BTN_ID)?.classList.remove('recording');
}

function _onStop() {
    const dur = (Date.now() - _startTime) / 1000;
    if (dur < 0.5) { _swapInputTo('normal'); return; }

    const mime = _mediaRecorder.mimeType;
    const ext  = mime.includes('ogg') ? 'ogg' : 'webm';
    const blob = new Blob(_chunks, { type: mime });
    const name = `voice_${Date.now()}.${ext}`;

    _swapInputTo('preview', { blob, name, mime, dur, peaks: [..._peaks] });
}

function _startPeaks() {
    const buf = new Uint8Array(_analyser?.frequencyBinCount || 128);
    _peakInterval = setInterval(() => {
        if (!_analyser) return;
        _analyser.getByteFrequencyData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i];
        const avg  = sum / buf.length;
        const logV = avg > 0 ? Math.log10(1 + avg) / Math.log10(256) : 0;
        _peaks.push(Math.min(1, logV));
    }, 80);
}

function _drawLiveWave() {
    const canvas = document.getElementById('vr-live-canvas');
    if (!canvas || !_analyser) return;
    const ctx = canvas.getContext('2d');
    const buf = new Uint8Array(_analyser.frequencyBinCount);

    function draw() {
        if (!_analyser) return;
        _animFrame = requestAnimationFrame(draw);
        _analyser.getByteTimeDomainData(buf);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.lineWidth   = 1.5;
        ctx.strokeStyle = 'rgba(200,220,255,0.6)';
        ctx.beginPath();
        const sw = canvas.width / buf.length;
        for (let i = 0; i < buf.length; i++) {
            const y = ((buf[i] / 128) * canvas.height) / 2;
            i === 0 ? ctx.moveTo(0, y) : ctx.lineTo(i * sw, y);
        }
        ctx.stroke();
    }
    draw();
}

function _swapInputTo(mode, data) {
    const area    = document.getElementById('input-area');
    const msgRow  = area?.querySelector('.input-row');

    document.getElementById('vr-record-ui')?.remove();
    document.getElementById('vr-preview-ui')?.remove();

    if (mode === 'normal') {
        if (msgRow) msgRow.style.display = '';
        return;
    }

    if (msgRow) msgRow.style.display = 'none';

    const ui = document.createElement('div');

    if (mode === 'record') {
        ui.id = 'vr-record-ui';
        ui.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;padding:6px 0;width:100%;">
                <span style="width:9px;height:9px;border-radius:50%;background:#ef4444;
                    flex-shrink:0;animation:recBlink 1s infinite;"></span>
                <span id="vr-timer" style="font-family:var(--mono);font-size:13px;
                    color:var(--text);min-width:38px;">0:00</span>
                <canvas id="vr-live-canvas" width="150" height="30" style="
                    flex:1;max-width:160px;border-radius:6px;
                    background:rgba(255,255,255,0.04);"></canvas>
                <button id="vr-stop" style="${_btnStyle('var(--accent)')}">■ Стоп</button>
                <button id="vr-cancel" style="${_iconBtnStyle()}">✕</button>
            </div>`;
        if (area) area.appendChild(ui);
        document.getElementById('vr-stop').onclick   = () => toggleVoiceRecording();
        document.getElementById('vr-cancel').onclick = () => window.cancelVoiceRecording();

    } else if (mode === 'preview') {
        const { blob, name, mime, dur, peaks } = data;
        ui.id = 'vr-preview-ui';

        const normPeaks = _normPeaks(peaks, 40);
        const url       = URL.createObjectURL(blob);
        const durStr    = _fmtDur(dur);

        ui.innerHTML = `
            <div style="display:flex;flex-direction:column;gap:8px;padding:6px 0;width:100%;">
                <div style="
                    display:flex;align-items:center;gap:10px;
                    padding:10px 14px;border-radius:14px;
                    background:rgba(148,158,178,0.09);
                    backdrop-filter:blur(20px) saturate(160%) brightness(1.07);
                    -webkit-backdrop-filter:blur(20px) saturate(160%) brightness(1.07);
                    border:1px solid rgba(255,255,255,0.12);
                    box-shadow:inset 0 1px 0 rgba(255,255,255,0.16),0 4px 18px rgba(0,0,0,.22);
                    position:relative;overflow:hidden;
                ">
                    <div style="position:absolute;inset:0;border-radius:inherit;pointer-events:none;
                        background:linear-gradient(135deg,rgba(255,255,255,0.10) 0%,transparent 55%);z-index:0;"></div>

                    <button id="vr-play-btn" style="
                        width:40px;height:40px;border-radius:50%;border:none;
                        display:flex;align-items:center;justify-content:center;
                        background:rgba(255,255,255,0.14);color:#fff;cursor:pointer;
                        box-shadow:0 2px 8px rgba(0,0,0,.3),inset 0 1px 0 rgba(255,255,255,.22);
                        flex-shrink:0;position:relative;z-index:1;transition:transform .12s;
                    ">${SVG_PLAY}</button>

                    <div style="flex:1;display:flex;flex-direction:column;gap:5px;min-width:0;position:relative;z-index:1;">
                        <div id="vr-bars" style="display:flex;align-items:center;gap:2px;height:32px;cursor:pointer;">
                            ${normPeaks.map(h =>
            `<div class="vrbar" style="flex:1;min-width:2px;border-radius:2px;
                                    height:${Math.max(12, h * 100)}%;
                                    background:rgba(200,215,240,0.22);
                                    transition:background .1s;"></div>`
        ).join('')}
                        </div>
                        <span id="vr-dur" style="font-family:var(--mono);font-size:11px;
                            color:rgba(255,255,255,0.38);">${durStr}</span>
                    </div>
                </div>

                <div style="display:flex;gap:8px;">
                    <button id="vr-send" style="${_btnStyle('var(--accent)', true)}">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="flex-shrink:0">
                            <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
                        </svg>
                        Отправить
                    </button>
                    <button id="vr-retry" title="Перезаписать"
                        style="${_btnStyle('var(--bg3)', false, true)}">🔄</button>
                    <button id="vr-cancel2" style="${_iconBtnStyle()}">✕</button>
                </div>
            </div>`;

        if (area) area.appendChild(ui);

        const audio    = new Audio(url);
        const playBtn  = document.getElementById('vr-play-btn');
        const barsEl   = document.getElementById('vr-bars');
        const durEl    = document.getElementById('vr-dur');
        const barNodes = barsEl ? Array.from(barsEl.querySelectorAll('.vrbar')) : [];
        const N        = barNodes.length;

        audio.addEventListener('timeupdate', () => {
            const pct    = audio.duration ? audio.currentTime / audio.duration : 0;
            const played = Math.round(pct * N);
            barNodes.forEach((b, i) => {
                b.style.background = i < played
                    ? 'rgba(200,215,240,0.70)'
                    : 'rgba(200,215,240,0.22)';
            });
            if (durEl) durEl.textContent = _fmtDur(audio.currentTime);
        });
        audio.addEventListener('ended', () => {
            if (playBtn) playBtn.innerHTML = SVG_PLAY;
            barNodes.forEach(b => b.style.background = 'rgba(175,180,195,0.18)');
            if (durEl) durEl.textContent = durStr;
        });
        if (barsEl) {
            barsEl.addEventListener('click', e => {
                if (!audio.duration) return;
                const r = barsEl.getBoundingClientRect();
                audio.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * audio.duration;
            });
        }
        if (playBtn) {
            playBtn.onclick = () => {
                if (audio.paused) { audio.play(); playBtn.innerHTML = SVG_PAUSE; }
                else              { audio.pause(); playBtn.innerHTML = SVG_PLAY; }
            };
        }

        document.getElementById('vr-send').onclick = async () => {
            const btn = document.getElementById('vr-send');
            btn.disabled = true;
            btn.textContent = '⏳ Отправка…';
            try {
                try { sessionStorage.setItem('vp:' + name, JSON.stringify(peaks)); } catch {}
                await _upload(blob, name, mime);
                audio.pause();
                URL.revokeObjectURL(url);
                _swapInputTo('normal');
            } catch (e) {
                btn.disabled = false;
                btn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                    <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/></svg> Отправить`;
                alert('Ошибка отправки: ' + e.message);
            }
        };

        document.getElementById('vr-retry').onclick = () => {
            audio.pause(); URL.revokeObjectURL(url);
            _swapInputTo('normal');
            toggleVoiceRecording();
        };

        document.getElementById('vr-cancel2').onclick = () => {
            audio.pause(); URL.revokeObjectURL(url);
            _swapInputTo('normal');
        };
    }
}

// ✅ Получаем свежий CSRF токен перед каждым запросом
async function _freshCsrf() {
    try {
        const r = await fetch('/api/authentication/csrf-token', { credentials: 'include' });
        if (r.ok) {
            const data = await r.json();
            // обновляем meta-тег на будущее
            const meta = document.querySelector('meta[name="csrf-token"]');
            if (meta && data.csrf_token) meta.content = data.csrf_token;
            return data.csrf_token || '';
        }
    } catch {}
    // fallback на cookie/meta
    return document.querySelector('meta[name="csrf-token"]')?.content ||
        document.cookie.split('; ').find(r => r.startsWith('csrf_token='))?.split('=')[1] || '';
}

async function _upload(blob, name, mime) {
    const S = window.AppState;
    if (!S?.currentRoom) throw new Error('Нет активной комнаты');

    const csrf = await _freshCsrf();   // ✅ всегда свежий токен

    if (S.ws?.readyState === WebSocket.OPEN)
        S.ws.send(JSON.stringify({ action: 'file_sending', filename: name }));

    const fd = new FormData();
    fd.append('file', new File([blob], name, { type: mime }));

    try {
        const res = await fetch(`/api/files/upload/${S.currentRoom.id}`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrf },
            credentials: 'include',
            body: fd,
        });
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`HTTP ${res.status}: ${text}`);
        }
    } finally {
        if (S.ws?.readyState === WebSocket.OPEN)
            S.ws.send(JSON.stringify({ action: 'stop_file_sending' }));
    }
}

function _normPeaks(peaks, N) {
    if (!peaks?.length) return Array(N).fill(0.3);
    const out = [];
    for (let i = 0; i < N; i++) {
        const s = Math.floor(i * peaks.length / N);
        const e = Math.max(s + 1, Math.floor((i + 1) * peaks.length / N));
        let mx  = 0;
        for (let j = s; j < e; j++) mx = Math.max(mx, peaks[j] || 0);
        out.push(mx);
    }
    const max = Math.max(...out, 0.01);
    return out.map(v => v / max);
}

function _btnStyle(bg, flex = false, border = false) {
    return `height:40px;padding:0 16px;border-radius:10px;
        background:${bg};border:${border ? '1px solid var(--border)' : 'none'};
        color:${bg === 'var(--bg3)' ? 'var(--text2)' : '#fff'};
        font-family:var(--sans);font-weight:700;font-size:13px;cursor:pointer;
        display:flex;align-items:center;justify-content:center;gap:6px;
        ${flex ? 'flex:1;' : ''}`;
}

function _iconBtnStyle() {
    return `width:40px;height:40px;border-radius:10px;flex-shrink:0;
        background:var(--bg3);border:1px solid var(--border);
        color:var(--text2);cursor:pointer;font-size:18px;
        display:flex;align-items:center;justify-content:center;`;
}

function _startTimer() {
    _timerInterval = setInterval(() => {
        const el  = document.getElementById('vr-timer');
        const sec = Math.floor((Date.now() - _startTime) / 1000);
        if (el) el.textContent = _fmtDur(sec);
        if (sec >= 300) _stopRecording();
    }, 500);
}

function _fmtDur(s) {
    if (!isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, '0')}`;
}

window.toggleVoiceRecording = toggleVoiceRecording;

window.cancelVoiceRecording = () => {
    if (_mediaRecorder?.state === 'recording') {
        _mediaRecorder.onstop = null;
        _mediaRecorder.stop();
    }
    _stream?.getTracks().forEach(t => t.stop());
    _stream = null;
    clearInterval(_timerInterval);
    clearInterval(_peakInterval);
    cancelAnimationFrame(_animFrame);
    _animFrame = null; _analyser = null; _chunks = [];
    _swapInputTo('normal');
    document.getElementById(VOICE_BTN_ID)?.classList.remove('recording');
};