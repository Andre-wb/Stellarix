// ── Hub ───────────────────────────────────────────────────────
function ideRenderHub() {
    const grid = document.getElementById('ide-projects-grid');
    if (!grid) return;
    grid.innerHTML = '';

    IDE.projects.forEach((p, idx) => {
        const card = document.createElement('div');
        card.className = 'ide-project-card';
        const isArx = p.lang === 'architex';
        const logoEl = isArx
            ? '<img src="/logo/architex.svg" width="24" height="24" alt="Architex" style="opacity:.9">'
            : '<img src="/logo/gravitix.svg" width="24" height="24" alt="Gravitix" style="opacity:.9">';
        card.innerHTML = `
            <div class="ide-project-card-icon">
                ${logoEl}
            </div>
            <div class="ide-project-card-info">
                <div class="ide-project-card-name">${_esc(p.name)}</div>
                <div class="ide-project-card-meta">${p.username ? '@'+_esc(p.username) : 'No bot linked'} · ${_relTime(p.created)}</div>
            </div>
            <div class="ide-project-card-actions">
                <button onclick="event.stopPropagation();ideDeleteProject(${idx})" title="Delete">
                    <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                </button>
            </div>`;
        card.onclick = () => ideOpenProject(idx);
        grid.appendChild(card);
    });

    // "New" card always last
    const newCard = document.createElement('div');
    newCard.className = 'ide-project-card ide-project-new';
    newCard.onclick = ideShowCreateModal;
    newCard.innerHTML = `
        <div class="ide-project-new-icon"><svg width="28" height="28" fill="currentColor" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg></div>
        <span>New Project</span>`;
    grid.appendChild(newCard);
}

// ── Create project ────────────────────────────────────────────
function ideShowCreateModal() {
    document.getElementById('ide-create-name').value     = '';
    document.getElementById('ide-create-token').value    = '';
    document.getElementById('ide-create-username').value = '';
    document.getElementById('ide-create-tutorial').checked = true;
    const dd = document.getElementById('ide-bots-dropdown');
    if (dd) dd.style.display = 'none';
    const uh = document.getElementById('ide-create-uname-hint');
    if (uh) uh.textContent = '';
    const ui = document.getElementById('ide-create-username');
    if (ui) ui.classList.remove('ide-input-ok', 'ide-input-err');
    document.getElementById('ide-create-overlay').style.display = 'flex';
    document.getElementById('ide-create-modal').classList.add('open');
    setTimeout(() => document.getElementById('ide-create-name').focus(), 100);
}

function ideHideCreateModal() {
    document.getElementById('ide-create-overlay').style.display = 'none';
    document.getElementById('ide-create-modal').classList.remove('open');
}

// ── Project settings ──────────────────────────────────────────
function ideShowSettings() {
    if (!IDE.current) return;
    document.getElementById('ide-settings-name').value        = IDE.current.name         || '';
    document.getElementById('ide-settings-token').value       = IDE.current.token        || '';
    document.getElementById('ide-settings-username').value    = IDE.current.username     || '';
    document.getElementById('ide-settings-miniapp-url').value = IDE.current.mini_app_url || '';
    // Reset token field to password mode
    const inp = document.getElementById('ide-settings-token');
    inp.type = 'password';
    document.getElementById('ide-eye-icon').innerHTML = '<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>';
    // Reset username validation display
    const uh = document.getElementById('ide-settings-uname-hint');
    if (uh) uh.textContent = '';
    const ui = document.getElementById('ide-settings-username');
    if (ui) { ui.classList.remove('ide-input-ok','ide-input-err'); }
    document.getElementById('ide-settings-overlay').style.display = 'flex';
    document.getElementById('ide-settings-modal').classList.add('open');
    setTimeout(() => document.getElementById('ide-settings-name').focus(), 100);
}

function ideHideSettings() {
    document.getElementById('ide-settings-overlay').style.display = 'none';
    document.getElementById('ide-settings-modal').classList.remove('open');
}

function ideSaveSettings() {
    if (!IDE.current) return;
    const name         = document.getElementById('ide-settings-name').value.trim();
    const token        = document.getElementById('ide-settings-token').value.trim();
    const username     = document.getElementById('ide-settings-username').value.trim().replace('@', '');
    const mini_app_url = document.getElementById('ide-settings-miniapp-url').value.trim();

    if (!name) {
        document.getElementById('ide-settings-name').focus();
        return;
    }

    IDE.current.name         = name;
    IDE.current.token        = token;
    IDE.current.username     = username;
    IDE.current.mini_app_url = mini_app_url;
    ideSave();

    // Update topbar label immediately
    document.getElementById('ide-topbar-project').textContent = name;
    ideUpdateTokenBtn();

    ideHideSettings();
}

function ideCopyToken(source) {
    const token = IDE.current && IDE.current.token;
    if (!token) {
        ideShowToast('No API token saved yet', 'warn');
        return;
    }
    navigator.clipboard.writeText(token).then(() => {
        if (source === 'modal') {
            const icon = document.getElementById('ide-copy-icon');
            if (icon) {
                icon.innerHTML = '<path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>';
                setTimeout(() => {
                    icon.innerHTML = '<path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>';
                }, 1500);
            }
        }
        ideShowToast('API token copied!', 'ok');
    }).catch(() => {
        ideShowToast('Copy failed — check browser permissions', 'warn');
    });
}

function ideShowToast(msg, type) {
    let toast = document.getElementById('ide-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'ide-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = 'ide-toast ide-toast-' + (type || 'ok') + ' ide-toast-show';
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove('ide-toast-show'), 2200);
}

function ideUpdateTokenBtn() {
    const btn = document.getElementById('ide-copy-token-btn');
    if (!btn) return;
    btn.style.display = (IDE.current && IDE.current.token) ? 'flex' : 'none';
}

function ideToggleTokenVis() {
    const inp  = document.getElementById('ide-settings-token');
    const icon = document.getElementById('ide-eye-icon');
    if (inp.type === 'password') {
        inp.type = 'text';
        icon.innerHTML = '<path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.804 11.804 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>';
    } else {
        inp.type = 'password';
        icon.innerHTML = '<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>';
    }
}

function ideToggleBotsMenu(e) {
    e.stopPropagation();
    const dd = document.getElementById('ide-bots-dropdown');
    if (!dd) return;

    if (dd.style.display !== 'none') { dd.style.display = 'none'; return; }

    // Populate
    const bots = IDE.projects.filter(p => p.token);
    if (bots.length === 0) {
        dd.innerHTML = '<div class="ide-bots-empty">No saved bots yet.<br>Add a token to an existing project first.</div>';
    } else {
        dd.innerHTML = bots.map((p, i) => {
            const uname = p.username ? `<span class="ide-bots-item-un">@${p.username}</span>` : '';
            const idx   = IDE.projects.indexOf(p);
            return `<button class="ide-bots-item" onclick="ideSelectSavedBot(${idx});event.stopPropagation()">
                <svg width="14" height="14" fill="#7c3aed" viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1.07A7.001 7.001 0 0 1 7.07 19H6a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h-1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2M7.5 13A2.5 2.5 0 0 0 5 15.5 2.5 2.5 0 0 0 7.5 18a2.5 2.5 0 0 0 2.5-2.5A2.5 2.5 0 0 0 7.5 13m9 0a2.5 2.5 0 0 0-2.5 2.5 2.5 2.5 0 0 0 2.5 2.5 2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5"/></svg>
                <div class="ide-bots-item-info">
                    <span class="ide-bots-item-name">${p.name}</span>
                    ${uname}
                </div>
            </button>`;
        }).join('');
    }

    dd.style.display = 'block';

    // Close on outside click
    const close = () => { dd.style.display = 'none'; document.removeEventListener('click', close); };
    setTimeout(() => document.addEventListener('click', close), 0);
}

function ideSelectSavedBot(idx) {
    const p = IDE.projects[idx];
    if (!p) return;
    const dd = document.getElementById('ide-bots-dropdown');
    if (dd) dd.style.display = 'none';

    document.getElementById('ide-create-token').value    = p.token    || '';
    document.getElementById('ide-create-username').value = p.username || '';
    ideValidateUsername('create');

    const nameEl = document.getElementById('ide-create-name');
    if (!nameEl.value.trim()) nameEl.value = p.name || '';
}

async function ideDetectBot(modal) {
    const tokenEl = document.getElementById(modal === 'create' ? 'ide-create-token' : 'ide-settings-token');
    const token = tokenEl.value.trim();
    if (!token) { ideShowToast('Enter a Bot Token first', 'warn'); return; }

    const detectBtn = modal === 'create'
        ? document.getElementById('ide-create-detect')
        : tokenEl.parentElement.querySelector('.ide-detect-btn');

    const origHTML = detectBtn.innerHTML;
    detectBtn.disabled = true;
    detectBtn.innerHTML = '<svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24" style="animation:ide-spin .7s linear infinite"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>';

    try {
        const res  = await fetch(`https://api.telegram.org/bot${token}/getMe`);
        const data = await res.json();
        if (!data.ok) throw new Error(data.description || 'Telegram API error');

        const bot  = data.result;
        const uname = bot.username || '';
        const fname = bot.first_name || '';

        if (modal === 'create') {
            const nameEl = document.getElementById('ide-create-name');
            if (!nameEl.value.trim()) nameEl.value = fname;
            document.getElementById('ide-create-username').value = uname;
            ideValidateUsername('create');
        } else {
            const nameEl = document.getElementById('ide-settings-name');
            if (!nameEl.value.trim()) nameEl.value = fname;
            document.getElementById('ide-settings-username').value = uname;
            ideValidateUsername('settings');
        }
        ideShowToast(`✓ Bot detected: @${uname}`, 'ok');
    } catch(e) {
        ideShowToast(`Detection failed: ${e.message}`, 'warn');
    } finally {
        detectBtn.disabled = false;
        detectBtn.innerHTML = origHTML;
    }
}

function ideValidateUsername(modal) {
    const input = document.getElementById(modal === 'create' ? 'ide-create-username' : 'ide-settings-username');
    const hint  = document.getElementById(modal === 'create' ? 'ide-create-uname-hint' : 'ide-settings-uname-hint');
    const val   = input.value.trim().replace(/^@/, '');
    input.value = val;

    if (!val) { hint.textContent = ''; input.classList.remove('ide-input-ok','ide-input-err'); return; }

    const valid = /^[a-zA-Z][a-zA-Z0-9_]{3,30}[bB][oO][tT]$/.test(val);
    if (valid) {
        hint.textContent = '✓';
        hint.style.color = '#4ade80';
        input.classList.add('ide-input-ok');
        input.classList.remove('ide-input-err');
    } else {
        hint.textContent = 'must end with "bot", 5–32 chars';
        hint.style.color = '#f87171';
        input.classList.remove('ide-input-ok');
        input.classList.add('ide-input-err');
    }
}

function ideCreateProject() {
    const name     = document.getElementById('ide-create-name').value.trim();
    const token    = document.getElementById('ide-create-token').value.trim();
    const username = document.getElementById('ide-create-username').value.trim().replace('@','');
    const tutorial = document.getElementById('ide-create-tutorial').checked;
    const langSel  = document.querySelector('input[name="ide-create-lang"]:checked');
    const lang     = langSel ? langSel.value : 'gravitix';
    const ext      = lang === 'architex' ? '.arx' : '.grav';

    if (!name) { document.getElementById('ide-create-name').focus(); return; }

    const files = {};
    if (tutorial) {
        const tutCode = lang === 'architex' ? TUTORIAL_CODE_ARX : TUTORIAL_CODE;
        files['tutorial' + ext] = tutCode;
        files['main' + ext]     = STARTER_CODE(name, lang);
    } else {
        files['main' + ext] = STARTER_CODE(name, lang);
    }

    // For Architex projects, also add a Gravitix bridge file
    if (lang === 'architex') {
        files['bot.grav'] = STARTER_CODE_GRAV(name);
    }
    // For Gravitix projects, add an Architex UI file
    if (lang === 'gravitix') {
        files['ui.arx'] = STARTER_CODE_ARX(name);
    }

    const project = { id: Date.now(), name, token, username, lang, created: Date.now(), files, folders: [] };
    IDE.projects.unshift(project);
    ideSave();
    ideHideCreateModal();
    ideRenderHub();
    ideOpenProject(0);
}

function ideDeleteProject(idx) {
    if (!confirm((typeof t==='function'?t('ide.deleteProjectConfirm'):'Delete project') + ` "${IDE.projects[idx].name}"?`)) return;
    IDE.projects.splice(idx, 1);
    ideSave();
    ideRenderHub();
}

// ── Open project ──────────────────────────────────────────────
function ideOpenProject(idx) {
    IDE.current   = IDE.projects[idx];
    IDE.openFiles = [];
    IDE.activeFile = null;

    document.getElementById('ide-hub').style.display    = 'none';
    document.getElementById('ide-editor').style.display = 'flex';
    document.getElementById('ide-topbar-project').textContent = IDE.current.name;
    ideUpdateTokenBtn();

    ideRenderFileTree();
    ideRenderTabs();

    // Auto-open main.grav
    const firstFile = Object.keys(IDE.current.files)[0];
    if (firstFile) ideOpenFile(firstFile);
}

function ideGoHub() {
    ideAutosave();
    IDE.current    = null;
    IDE.openFiles  = [];
    IDE.activeFile = null;
    ideUpdateTokenBtn();
    document.getElementById('ide-editor').style.display = 'none';
    document.getElementById('ide-hub').style.display    = 'flex';
    // Hide simulator and preview if open
    if (IDE.simVisible) ideToggleSim();
    if (IDE.previewVisible) ideHidePreview();
    ideRenderHub();
}
