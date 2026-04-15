// node_setup/static/js/setup/step-network.js — шаг 2: режим сети и регистрации

/**
 * Выбирает режим сети (local / global) и обновляет интерфейс.
 * @param {string} mode
 */
function selectNetworkMode(mode) {
    _networkMode = mode;
    document.getElementById('opt-local').classList.toggle('selected', mode === 'local');
    document.getElementById('opt-global').classList.toggle('selected', mode === 'global');
    document.getElementById('global-details').style.display = mode === 'global' ? '' : 'none';

    if (mode === 'global') {
        _checkCloudflared();
    }
}

/**
 * Выбирает режим регистрации (open / invite / closed) и обновляет интерфейс.
 * @param {string} mode
 */
function selectRegMode(mode) {
    _regMode = mode;
    document.getElementById('opt-reg-open').classList.toggle('selected', mode === 'open');
    document.getElementById('opt-reg-invite').classList.toggle('selected', mode === 'invite');
    document.getElementById('opt-reg-closed').classList.toggle('selected', mode === 'closed');

    const inviteDisplay = document.getElementById('invite-code-display');
    if (mode === 'invite') {
        if (!_inviteCode) {
            _inviteCode = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                .map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase();
        }
        document.getElementById('generated-invite').textContent = _inviteCode;
        inviteDisplay.style.display = '';
    } else {
        inviteDisplay.style.display = 'none';
    }
}

/**
 * Проверяет, установлен ли cloudflared (для глобального режима).
 */
async function _checkCloudflared() {
    const el = document.getElementById('cf-status');
    try {
        const r = await fetch('/api/check-cloudflared');
        const data = await r.json();
        if (data.installed) {
            el.className = 'alert alert-success show';
            el.textContent = '✓ cloudflared installed — tunnel will start automatically';
        } else {
            el.className = 'alert alert-error show';
            el.innerHTML = '⚠ cloudflared not found.<br>Install: <code>brew install cloudflared</code> (macOS) or <code>sudo apt install cloudflared</code> (Linux).<br>Without it, global mode will only work via direct IP.';
        }
    } catch {
        el.className = 'alert show';
        el.textContent = 'Failed to check cloudflared';
    }
}

/**
 * Обработчик кнопки "Продолжить" на шаге 2 (Режим сети).
 */
function step2ModeNext() {
    _setStep(3);
}
