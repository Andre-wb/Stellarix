// node_setup/static/js/setup/step-sso.js — шаг 4: SSO / аутентификация

let _ssoProviders = [];

const _SSO_FIELDS = {
    google:    [{ id: 'client_id',     label: 'Client ID',     ph: '...apps.googleusercontent.com' },
                { id: 'client_secret', label: 'Client Secret', ph: 'GOCSPX-...' }],
    github:    [{ id: 'client_id',     label: 'Client ID',     ph: 'Ov23li...' },
                { id: 'client_secret', label: 'Client Secret', ph: 'ghc_...' }],
    apple:     [{ id: 'client_id',   label: 'Service ID',           ph: 'com.example.vortex' },
                { id: 'team_id',     label: 'Team ID',              ph: 'ABCD123456' },
                { id: 'key_id',      label: 'Key ID',               ph: 'ABCDEF1234' },
                { id: 'private_key', label: 'Private Key (.p8)',     ph: '-----BEGIN PRIVATE KEY-----\n...', ml: true }],
    microsoft: [{ id: 'tenant_id',     label: 'Tenant ID',     ph: 'common or tenant UUID' },
                { id: 'client_id',     label: 'Client ID',     ph: 'UUID...' },
                { id: 'client_secret', label: 'Client Secret', ph: 'value...' }],
    oidc:      [{ id: 'discovery_url', label: 'Discovery URL', ph: 'https://keycloak.host/realms/main/.well-known/openid-configuration' },
                { id: 'client_id',     label: 'Client ID',     ph: 'vortex' },
                { id: 'client_secret', label: 'Client Secret', ph: '...' }],
};

const _SSO_LABELS = { google: 'Google', github: 'GitHub', apple: 'Apple Sign In', microsoft: 'Microsoft / Azure AD', oidc: 'Generic OIDC' };
const _SSO_ICONS  = { google: '🔵', github: '⚫', apple: '⚪', microsoft: '🔷', oidc: '🔑' };

function ssoTypeChanged() {
    const type   = document.getElementById('sso-type-select').value;
    const fields = _SSO_FIELDS[type] || [];
    document.getElementById('sso-dynamic-fields').innerHTML = fields.map(f =>
        `<div class="form-group">
            <label class="form-label">${esc(f.label)}</label>
            ${f.ml
                ? `<textarea class="form-input" id="sso-field-${f.id}" placeholder="${esc(f.ph)}" rows="4" style="font-family:var(--mono);font-size:11px;resize:vertical;"></textarea>`
                : `<input class="form-input" id="sso-field-${f.id}" type="text" placeholder="${esc(f.ph)}" autocomplete="off">`
            }
        </div>`
    ).join('');
}

function ssoShowPanel() {
    document.getElementById('sso-add-panel').style.display = '';
    document.getElementById('sso-add-btn').style.display   = 'none';
    document.getElementById('sso-type-select').value       = '';
    document.getElementById('sso-dynamic-fields').innerHTML = '';
}

function ssoHidePanel() {
    document.getElementById('sso-add-panel').style.display = 'none';
    document.getElementById('sso-add-btn').style.display   = '';
}

function ssoAddProvider() {
    const type = document.getElementById('sso-type-select').value;
    if (!type) return showAlert('s4-sso', 'Select a provider', 'error');
    if (_ssoProviders.find(p => p.type === type))
        return showAlert('s4-sso', `${_SSO_LABELS[type]} already added`, 'error');

    const data   = { type };
    const fields = _SSO_FIELDS[type] || [];
    for (const f of fields) {
        const el  = document.getElementById('sso-field-' + f.id);
        if (!el) continue;
        const val = el.value.trim();
        if (!val) return showAlert('s4-sso', `Fill in the field: ${f.label}`, 'error');
        data[f.id] = val;
    }
    _ssoProviders.push(data);
    hideAlert('s4-sso');
    ssoHidePanel();
    _renderSsoList();
}

function ssoRemoveProvider(type) {
    _ssoProviders = _ssoProviders.filter(p => p.type !== type);
    _renderSsoList();
}

function _renderSsoList() {
    const list = document.getElementById('sso-providers-list');
    if (!_ssoProviders.length) {
        list.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:6px 0 14px;">No providers added</div>';
        return;
    }
    list.innerHTML = _ssoProviders.map(p => `
        <div style="display:flex;align-items:center;padding:12px 16px;background:var(--bg3);border-radius:var(--radius);margin-bottom:8px;gap:12px;border:1px solid var(--border);">
            <span style="font-size:20px;">${_SSO_ICONS[p.type] || '🔐'}</span>
            <div style="flex:1;">
                <div style="font-weight:600;font-size:13px;">${esc(_SSO_LABELS[p.type] || p.type)}</div>
                <div style="font-size:11px;color:var(--text3);">${esc(p.client_id || p.discovery_url || '')}</div>
            </div>
            <button onclick="ssoRemoveProvider('${p.type}')"
                    style="background:none;border:none;color:var(--red,#f87171);cursor:pointer;padding:4px;line-height:0;"
                    title="Delete">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6zM19 4h-3.5l-1-1h-5l-1 1H5v2h14z"/></svg>
            </button>
        </div>
    `).join('');
}

async function _saveSsoToServer() {
    const passkeys = document.getElementById('passkeys-toggle')?.checked ?? true;
    const r = await fetch('/api/sso/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passkeys_enabled: passkeys, providers: _ssoProviders }),
    });
    if (!r.ok) throw new Error('Error saving SSO configuration');
}

async function ssoProceed() {
    try {
        await _saveSsoToServer();
    } catch (e) {
        showAlert('s4-sso', e.message, 'error');
        return;
    }
    await buildSummary();
    _setStep(5);
}

async function ssoSkip() {
    try { await _saveSsoToServer(); } catch { /* не критично */ }
    await buildSummary();
    _setStep(5);
}
