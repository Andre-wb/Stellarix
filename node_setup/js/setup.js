// ── State ─────────────────────────────────────────────────────────────────────
const state = {
    step:       1,
    sslMode:    'self',
    sslDone:    false,
    sslSkipped: false,
    caCmd:      '',
    nodeUrl:    '',
    sysInfo:    null,
    config:     null,
};

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
    await loadSysInfo();
    prefillDeviceName();
    checkMkcert();
    bindPortValidation();
});

async function loadSysInfo() {
    try {
        const r    = await fetch('/api/info');
        state.sysInfo = await r.json();
        const ip   = state.sysInfo.local_ips?.[0] || 'не определён';
        const ok   = ip !== 'не определён';
        document.getElementById('ip-dot').className  = 'dot ' + (ok ? 'dot-green' : 'dot-yellow');
        document.getElementById('ip-text').textContent = `Локальный IP: ${ip}`;
    } catch {
        document.getElementById('ip-text').textContent = 'Не удалось определить IP';
    }
}

function prefillDeviceName() {
    if (state.sysInfo?.hostname) {
        document.getElementById('device-name').value = state.sysInfo.hostname;
    }
}

function checkMkcert() {
    const avail = state.sysInfo?.ssl_methods?.mkcert;
    const opt   = document.getElementById('opt-mkcert');
    const badge = document.getElementById('mkcert-badge');
    if (avail) {
        badge.textContent = '✓ Установлен';
        badge.className   = 'ssl-badge badge-recommended';
    } else {
        opt.classList.add('unavailable');
        badge.textContent = 'Не установлен';
        badge.className   = 'ssl-badge badge-advanced';
    }
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goStep(n) {
    if (n > state.step) return;
    _setStep(n);
}

function _setStep(n) {
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
    document.getElementById('step-' + n).classList.add('active');

    for (let i = 1; i <= 4; i++) {
        const dot  = document.getElementById('sdot-' + i);
        const line = document.getElementById('sline-' + i);
        dot.classList.remove('active', 'done');
        if (line) line.classList.remove('done');
        if (i < n)  { dot.classList.add('done');   if (line) line.classList.add('done'); }
        if (i === n) { dot.classList.add('active'); }
    }

    state.step = n;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Step 1: Node config ───────────────────────────────────────────────────────
async function step1Next() {
    const name = document.getElementById('device-name').value.trim();
    const port = parseInt(document.getElementById('node-port').value);
    const udp  = parseInt(document.getElementById('udp-port').value);
    const mfmb = parseInt(document.getElementById('max-file').value);

    if (!name) return showAlert('s1', 'Введите имя устройства', 'error');
    if (isNaN(port) || port < 1024 || port > 65535)
        return showAlert('s1', 'Неверный порт (1024–65535)', 'error');

    const btn = document.getElementById('btn-s1-next');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Проверка порта...';

    try {
        const r = await fetch(`/api/validate/port/${port}`);
        const d = await r.json();
        if (!d.ok) {
            showAlert('s1', d.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Продолжить →';
            return;
        }
    } catch { /* порт недоступен для проверки — пропускаем */ }

    btn.disabled = false;
    btn.textContent = 'Продолжить →';
    hideAlert('s1');

    state.config = { device_name: name, port, udp_port: udp, max_file_mb: mfmb };
    _setStep(2);
}

// ── Step 2: SSL ───────────────────────────────────────────────────────────────
function selectSSL(mode) {
    state.sslMode = mode;

    ['self', 'mkcert', 'le', 'skip'].forEach(m => {
        document.getElementById('opt-' + m)?.classList.remove('selected');
        document.getElementById('detail-' + m)?.classList.remove('active');
    });

    document.getElementById('opt-' + mode).classList.add('selected');
    document.getElementById('detail-' + mode).classList.add('active');

    document.getElementById('btn-ssl-gen').textContent =
        mode === 'skip' ? 'Пропустить SSL →' : '🔒 Сгенерировать →';
}

async function generateSSL() {
    const btn      = document.getElementById('btn-ssl-gen');
    const block    = document.getElementById('ssl-gen-block');
    const terminal = document.getElementById('ssl-terminal');

    btn.disabled   = true;
    btn.innerHTML  = '<span class="spinner"></span> Генерация...';
    block.style.display = 'block';
    terminal.innerHTML  = '';

    const log = (text, cls = 'line-dim') => {
        terminal.innerHTML += `<div class="${cls}">${text}</div>`;
        terminal.scrollTop  = 99999;
    };

    try {
        switch (state.sslMode) {

            case 'skip': {
                log('⚡ SSL пропущен. Узел будет работать по HTTP.', 'line-warn');
                state.sslDone    = true;
                state.sslSkipped = true;
                await buildSummary();
                _setStep(3);
                break;
            }

            case 'self': {
                log('⚡ Генерация CA и серверного сертификата...', 'line-info');
                const body = {
                    org_name:   document.getElementById('ssl-org').value || 'Vortex Node',
                    install_ca: document.getElementById('install-ca').checked,
                };
                const r = await fetch('/api/ssl/self-signed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const d = await r.json();
                if (!r.ok) throw new Error(d.detail || d.message);

                log(`✓ CA:   ${d.ca}`,   'line-ok');
                log(`✓ CERT: ${d.cert}`, 'line-ok');
                log(`✓ KEY:  ${d.key}`,  'line-ok');
                log(d.trusted
                        ? '✓ CA установлен в системное хранилище'
                        : '⚠ CA не установлен автоматически',
                    d.trusted ? 'line-ok' : 'line-warn');

                state.caCmd   = d.ca_install || '';
                state.sslDone = true;
                await buildSummary(d);
                _setStep(3);
                break;
            }

            case 'mkcert': {
                log('⚡ Запуск mkcert...', 'line-info');
                const r = await fetch('/api/ssl/mkcert', { method: 'POST' });
                const d = await r.json();
                if (!r.ok) throw new Error(d.detail || d.message);
                log(`✓ ${d.message}`, 'line-ok');
                state.sslDone = true;
                await buildSummary(d);
                _setStep(3);
                break;
            }

            case 'le': {
                const domain  = document.getElementById('le-domain').value.trim();
                const email   = document.getElementById('le-email').value.trim();
                const staging = document.getElementById('le-staging').checked;
                if (!domain) { showAlert('s2', 'Введите домен', 'error');  return; }
                if (!email)  { showAlert('s2', 'Введите email', 'error');  return; }

                log(`⚡ certbot: получение сертификата для ${domain}...`, 'line-info');
                const r = await fetch('/api/ssl/letsencrypt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ domain, email, staging }),
                });
                const d = await r.json();
                if (!r.ok) throw new Error(d.detail || d.message);
                log(`✓ ${d.message}`, 'line-ok');
                state.sslDone = true;
                await buildSummary(d);
                _setStep(3);
                break;
            }
        }

    } catch (e) {
        log(`✗ Ошибка: ${e.message}`, 'line-err');
        showAlert('s2', e.message, 'error');

    } finally {
        btn.disabled    = false;
        btn.textContent = state.sslMode === 'skip' ? 'Пропустить SSL →' : '🔒 Сгенерировать →';
    }
}

// ── Step 3: Summary ───────────────────────────────────────────────────────────
async function buildSummary() {
    const cfg   = state.config;
    const proto = state.sslSkipped ? 'http' : 'https';
    const ssl   = state.sslSkipped ? '✗ HTTP (без SSL)' : '✓ HTTPS';
    const modes = { self: 'Самоподписанный', mkcert: 'mkcert', le: "Let's Encrypt", skip: 'Отключён' };
    const ip    = state.sysInfo?.local_ips?.[0] || '—';

    state.nodeUrl = `${proto}://localhost:${cfg.port}`;

    document.getElementById('summary-list').innerHTML = `
    <li>
      <span class="label">Имя устройства</span>
      <span class="value">${esc(cfg.device_name)}</span>
    </li>
    <li>
      <span class="label">Адрес</span>
      <span class="value" style="color:var(--teal)">${state.nodeUrl}</span>
    </li>
    <li>
      <span class="label">Локальный IP</span>
      <span class="value">${ip}:${cfg.port}</span>
    </li>
    <li>
      <span class="label">SSL</span>
      <span class="value" style="color:${state.sslSkipped ? 'var(--yellow)' : 'var(--green)'}">
        ${ssl} (${modes[state.sslMode]})
      </span>
    </li>
    <li>
      <span class="label">P2P UDP порт</span>
      <span class="value">${cfg.udp_port}</span>
    </li>
    <li>
      <span class="label">Макс. файл</span>
      <span class="value">${cfg.max_file_mb} МБ</span>
    </li>
  `;

    if (state.caCmd) {
        document.getElementById('ca-install-block').style.display = 'block';
        document.getElementById('ca-cmd-text').textContent = state.caCmd;
    }
}

// ── Step 4: Launch ────────────────────────────────────────────────────────────
async function launchNode() {
    const btn = document.getElementById('btn-launch');
    btn.disabled  = true;
    btn.innerHTML = '<span class="spinner"></span> Сохранение...';

    try {
        const r1 = await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state.config),
        });
        if (!r1.ok) throw new Error((await r1.json()).detail || 'Ошибка сохранения конфига');

        const r2 = await fetch('/api/setup/complete', { method: 'POST' });
        const d2 = await r2.json();
        if (!r2.ok) throw new Error(d2.detail || 'Ошибка');

        document.getElementById('node-url').textContent = state.nodeUrl;

        if (state.caCmd) {
            document.getElementById('ca-warn-block').style.display = 'block';
            document.getElementById('ca-final').textContent = state.caCmd;
        }

        _setStep(4);
        startRedirectCountdown();

    } catch (e) {
        showAlert('s3', e.message, 'error');
        btn.disabled    = false;
        btn.textContent = '⚡ Запустить узел';
    }
}

function startRedirectCountdown() {
    let secs     = 5;
    const bar    = document.getElementById('redirect-bar');
    const text   = document.getElementById('redirect-text');
    const tick   = setInterval(() => {
        secs--;
        bar.style.width     = ((5 - secs) / 5 * 100) + '%';
        text.textContent    = `Переход через ${secs} секунд...`;
        if (secs <= 0) { clearInterval(tick); openNodeUrl(); }
    }, 1000);
}

function openNodeUrl() {
    if (state.nodeUrl) window.open(state.nodeUrl, '_blank');
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function showAlert(sid, msg, type = 'error') {
    const el = document.getElementById('alert-' + sid);
    if (!el) return;
    el.textContent = msg;
    el.className   = `alert show alert-${type}`;
}

function hideAlert(sid) {
    document.getElementById('alert-' + sid)?.classList.remove('show');
}

function esc(s) {
    return String(s || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function copyCode(id) {
    const el   = document.getElementById(id);
    const text = el.querySelector('span')?.textContent || el.textContent;
    navigator.clipboard.writeText(text.trim()).then(() => {
        const btn = el.querySelector('.code-copy');
        if (btn) { btn.textContent = '✓'; setTimeout(() => btn.textContent = 'copy', 1500); }
    });
}

// ── Port validation ───────────────────────────────────────────────────────────
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
        } catch { /* игнорируем */ }
    }, 500));
}

function debounce(fn, ms) {
    let t;
    return function (...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), ms);
    };
}