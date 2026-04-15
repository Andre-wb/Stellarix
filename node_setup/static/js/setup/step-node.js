// node_setup/static/js/setup/step-node.js — шаг 1: настройка узла

/**
 * Заполняет поле имени устройства (device-name) значением hostname из sysInfo.
 */
function prefillDeviceName() {
    if (state.sysInfo?.hostname) {
        document.getElementById('device-name').value = state.sysInfo.hostname;
    }
}

/**
 * Обработчик кнопки "Продолжить" на шаге 1.
 * Проверяет поля, валидирует порт через API, сохраняет конфиг в state и переходит на шаг 2.
 */
async function step1Next() {
    const name = document.getElementById('device-name').value.trim();
    const port = parseInt(document.getElementById('node-port').value);
    const udp  = parseInt(document.getElementById('udp-port').value);
    const mfmb = parseInt(document.getElementById('max-file').value);

    if (!name) return showAlert('s1', 'Enter device name', 'error');
    if (isNaN(port) || port < 1024 || port > 65535)
        return showAlert('s1', 'Invalid port (1024–65535)', 'error');

    const btn = document.getElementById('btn-s1-next');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Checking port...';

    try {
        const r = await fetch(`/api/validate/port/${port}`);
        const d = await r.json();
        if (!d.ok) {
            showAlert('s1', d.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Continue →';
            return;
        }
    } catch { /* port check unavailable — skip */ }

    btn.disabled = false;
    btn.textContent = 'Continue →';
    hideAlert('s1');

    state.config = { device_name: name, port, udp_port: udp, max_file_mb: mfmb };
    _setStep(2);
}

/**
 * Привязывает обработчик input к полю node-port для валидации порта через API.
 */
function bindPortValidation() {
    document.getElementById('node-port')?.addEventListener('input', debounce(async function () {
        const port = parseInt(this.value);
        const hint = document.getElementById('port-hint');
        if (isNaN(port)) return;
        try {
            const r = await fetch(`/api/validate/port/${port}`);
            const d = await r.json();
            hint.textContent = d.message;
            hint.className   = 'form-hint ' + (d.ok ? 'ok' : 'error');
            this.className   = 'form-input ' + (d.ok ? 'ok' : 'error');
        } catch { /* игнорируем ошибки сети */ }
    }, 500));
}
