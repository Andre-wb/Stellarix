// ══════════════════════════════════════════════════════════════════════════════
// Bot Management UI
// ══════════════════════════════════════════════════════════════════════════════

window.showCreateBotForm = function() {
    var form = document.getElementById('create-bot-form');
    if (form) form.style.display = '';
};

window.hideCreateBotForm = function() {
    var form = document.getElementById('create-bot-form');
    if (form) form.style.display = 'none';
    var nameInput = document.getElementById('bot-name');
    var descInput = document.getElementById('bot-description');
    if (nameInput) nameInput.value = '';
    if (descInput) descInput.value = '';
};

window.createBot = async function() {
    var name = document.getElementById('bot-name')?.value?.trim();
    var description = document.getElementById('bot-description')?.value?.trim() || '';
    if (!name || name.length < 2) {
        window.vxAlert(t('bots.nameTooShort'));
        return;
    }
    try {
        var resp = await window.api('POST', '/api/bots', { name: name, description: description });
        if (resp.ok) {
            window.hideCreateBotForm();
            window.loadMyBots();
            await window.vxAlert(
                t('bots.createdTitle'),
                { token: resp.api_token }
            );
        }
    } catch (e) {
        window.vxAlert(t('bots.error') + ': ' + (e.message || e));
    }
};

window.loadMyBots = async function() {
    var container = document.getElementById('bots-list');
    if (!container) return;
    try {
        var resp = await window.api('GET', '/api/bots');
        var bots = resp.bots || [];
        if (bots.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('bots.noBots') + '</div>';
            return;
        }
        container.innerHTML = bots.map(function(b) {
            var statusDot = b.is_active
                ? '<span style="width:8px;height:8px;border-radius:50%;background:#27ae60;display:inline-block;"></span>'
                : '<span style="width:8px;height:8px;border-radius:50%;background:var(--text3);display:inline-block;"></span>';
            return '<div class="bot-card" onclick="openBotSettings(' + b.bot_id + ')" style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px 16px;cursor:pointer;display:flex;align-items:center;gap:12px;transition:border-color .15s;"' +
                ' onmouseenter="this.style.borderColor=\'var(--accent)\'" onmouseleave="this.style.borderColor=\'var(--border)\'">' +
                '<div style="width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,var(--accent),#3b82f6);display:flex;align-items:center;justify-content:center;flex-shrink:0;">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="#fff" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>' +
                '</div>' +
                '<div style="flex:1;min-width:0;">' +
                    '<div style="display:flex;align-items:center;gap:6px;">' +
                        '<span style="font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + _escBot(b.name) + '</span>' +
                        statusDot +
                    '</div>' +
                    '<div style="font-size:11px;color:var(--text3);font-family:var(--mono);">@' + _escBot(b.username) + '</div>' +
                '</div>' +
                '<div style="flex-shrink:0;color:var(--text3);">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>' +
                '</div>' +
            '</div>';
        }).join('');
    } catch (e) {
        container.innerHTML = '<div style="text-align:center;color:var(--danger);font-size:12px;padding:24px 0;">' + t('bots.loadError') + ': ' + _escBot(e.message || String(e)) + '</div>';
    }
};

function _escBot(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ══════════════════════════════════════════════════════════════════════════════
// Bot Settings Panel — full screen settings for a single bot
// ══════════════════════════════════════════════════════════════════════════════

window.openBotSettings = async function(botId) {
    // Remove existing panel
    document.getElementById('bot-settings-panel')?.remove();

    var panel = document.createElement('div');
    panel.id = 'bot-settings-panel';
    panel.style.cssText = 'position:fixed;inset:0;z-index:500;background:var(--bg);display:flex;flex-direction:column;overflow-y:auto;';

    panel.innerHTML = '<div style="padding:16px 20px;text-align:center;color:var(--text3);">' + t('common.loading') + '</div>';
    document.body.appendChild(panel);

    try {
        var resp = await window.api('GET', '/api/bots/' + botId + '/detail');
        var b = resp.bot || resp;

        var statusText = b.is_active ? t('bots.statusActive') : t('bots.statusDisabled');
        var statusColor = b.is_active ? '#27ae60' : 'var(--text3)';
        var cmds = (b.commands || []).map(function(c) {
            return '<div style="display:flex;gap:8px;align-items:baseline;padding:4px 0;">' +
                '<code style="color:var(--accent);font-weight:600;">' + _escBot(c.command) + '</code>' +
                '<span style="color:var(--text2);font-size:12px;">' + _escBot(c.description || '') + '</span></div>';
        }).join('');

        panel.innerHTML =
            // Header
            '<div style="display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--border);flex-shrink:0;">' +
                '<button onclick="document.getElementById(\'bot-settings-panel\')?.remove()" style="background:none;border:none;color:var(--text2);cursor:pointer;padding:4px;">' +
                    '<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>' +
                '</button>' +
                '<span style="font-weight:700;font-size:16px;flex:1;">' + t('bots.botSettings') + '</span>' +
                '<button onclick="deleteBot(' + botId + ');document.getElementById(\'bot-settings-panel\')?.remove()" style="background:none;border:none;color:var(--red);cursor:pointer;padding:4px;" title="' + t('app.delete') + '">' +
                    '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
                '</button>' +
            '</div>' +

            // Bot avatar + name
            '<div style="text-align:center;padding:24px 20px 16px;">' +
                '<div style="width:64px;height:64px;border-radius:16px;background:linear-gradient(135deg,var(--accent),#3b82f6);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="#fff" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>' +
                '</div>' +
                '<div style="font-weight:700;font-size:18px;">' + _escBot(b.name) + '</div>' +
                '<div style="font-size:12px;color:var(--text3);font-family:var(--mono);">@' + _escBot(b.username) + '</div>' +
                '<div style="display:flex;align-items:center;justify-content:center;gap:6px;margin-top:6px;">' +
                    '<span style="width:8px;height:8px;border-radius:50%;background:' + statusColor + ';"></span>' +
                    '<span style="font-size:12px;color:' + statusColor + ';">' + statusText + '</span>' +
                '</div>' +
                (b.description ? '<div style="font-size:13px;color:var(--text2);margin-top:8px;max-width:300px;margin-left:auto;margin-right:auto;">' + _escBot(b.description) + '</div>' : '') +
            '</div>' +

            // Settings sections
            '<div style="padding:0 20px 24px;display:flex;flex-direction:column;gap:12px;">' +

                // API Token
                '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px 16px;">' +
                    '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('bots.apiToken') + '</div>' +
                    '<div style="display:flex;gap:8px;">' +
                        '<button class="btn btn-secondary" onclick="copyBotToken(' + botId + ')" style="flex:1;font-size:12px;">' +
                            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:4px;"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>' +
                            t('bots.getToken') +
                        '</button>' +
                        '<button class="btn btn-secondary" onclick="regenerateBotToken(' + botId + ')" style="font-size:12px;color:var(--red);">' +
                            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:4px;"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
                            t('bots.regenerate') +
                        '</button>' +
                    '</div>' +
                '</div>' +

                // Constructor button
                '<button onclick="openBotConstructor(' + botId + ')" style="width:100%;display:flex;align-items:center;gap:12px;padding:14px 16px;background:linear-gradient(135deg,var(--accent),#3b82f6);border:none;border-radius:12px;cursor:pointer;transition:opacity .15s;" onmouseenter="this.style.opacity=\'0.9\'" onmouseleave="this.style.opacity=\'1\'">' +
                    '<svg width="24" height="24" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>' +
                    '<div style="text-align:left;">' +
                        '<div style="color:#fff;font-weight:700;font-size:14px;">' + t('botConstructor.title') + '</div>' +
                        '<div style="color:rgba(255,255,255,0.7);font-size:11px;">' + t('botConstructor.subtitle') + '</div>' +
                    '</div>' +
                    '<svg width="20" height="20" fill="none" stroke="rgba(255,255,255,0.6)" stroke-width="2" viewBox="0 0 24 24" style="margin-left:auto;"><polyline points="9 18 15 12 9 6"/></svg>' +
                '</button>' +

                // Commands preview
                (cmds ? '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px 16px;">' +
                    '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('bots.commands') + '</div>' +
                    cmds + '</div>' : '') +

                // Marketplace
                '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px 16px;">' +
                    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">' +
                        '<span style="font-weight:600;font-size:13px;">' + t('bots.marketplace') + '</span>' +
                        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;">' +
                            '<input type="checkbox" ' + (b.is_public ? 'checked' : '') + ' onchange="toggleBotPublish(' + botId + ',this.checked,document.getElementById(\'bot-cat-' + botId + '\').value)" style="width:16px;height:16px;accent-color:var(--accent);">' +
                            '<span style="font-size:12px;">' + t('bots.publishToMarketplace') + '</span>' +
                        '</label>' +
                    '</div>' +
                    '<select id="bot-cat-' + botId + '" style="width:100%;font-size:12px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);" onchange="if(document.querySelector(\'input[onchange*=toggleBotPublish]\')?.checked)toggleBotPublish(' + botId + ',true,this.value)">' +
                        '<option value="utilities"' + (b.category==='utilities'?' selected':'') + '>' + t('bots.catUtilities') + '</option>' +
                        '<option value="games"' + (b.category==='games'?' selected':'') + '>' + t('bots.catGames') + '</option>' +
                        '<option value="moderation"' + (b.category==='moderation'?' selected':'') + '>' + t('bots.catModeration') + '</option>' +
                        '<option value="music"' + (b.category==='music'?' selected':'') + '>' + t('bots.catMusic') + '</option>' +
                        '<option value="productivity"' + (b.category==='productivity'?' selected':'') + '>' + t('bots.catProductivity') + '</option>' +
                        '<option value="social"' + (b.category==='social'?' selected':'') + '>' + t('bots.catSocial') + '</option>' +
                        '<option value="fun"' + (b.category==='fun'?' selected':'') + '>' + t('bots.catFun') + '</option>' +
                        '<option value="other"' + (b.category==='other'?' selected':'') + '>' + t('bots.catOther') + '</option>' +
                    '</select>' +
                    (b.is_public ? '<div style="font-size:11px;color:var(--text3);margin-top:8px;">' +
                        t('bots.installsCount', {count: b.installs || 0}) + ' · ' +
                        '★ ' + _escBot(String(b.rating || 0)) + ' (' + t('bots.ratingsCount', {count: b.rating_count || 0}) + ')' +
                    '</div>' : '') +
                '</div>' +

            '</div>';

    } catch (e) {
        panel.innerHTML = '<div style="padding:40px;text-align:center;">' +
            '<div style="color:var(--red);margin-bottom:12px;">' + t('errors.loadingError') + '</div>' +
            '<button class="btn btn-secondary" onclick="document.getElementById(\'bot-settings-panel\')?.remove()">' + t('app.close') + '</button>' +
        '</div>';
    }
};

window.copyBotToken = async function(botId) {
    try {
        var resp = await window.api('GET', '/api/bots/' + botId + '/token');
        if (resp.api_token) {
            await window.vxAlert('API Token', { token: resp.api_token });
        }
    } catch (e) {
        window.vxAlert(t('bots.error') + ': ' + (e.message || e));
    }
};

window.regenerateBotToken = async function(botId) {
    if (!await window.vxConfirm(t('bots.regenerateTokenConfirm'), { danger: true })) return;
    try {
        var resp = await window.api('POST', '/api/bots/' + botId + '/regenerate-token');
        if (resp.ok) {
            await window.vxAlert(
                t('bots.newTokenTitle'),
                { token: resp.api_token }
            );
            window.loadMyBots();
        }
    } catch (e) {
        window.vxAlert(t('bots.error') + ': ' + (e.message || e));
    }
};

window.deleteBot = async function(botId) {
    if (!await window.vxConfirm(t('bots.deleteBotConfirm'), { danger: true })) return;
    try {
        var resp = await window.api('DELETE', '/api/bots/' + botId);
        if (resp.ok) {
            window.loadMyBots();
        }
    } catch (e) {
        window.vxAlert(t('bots.error') + ': ' + (e.message || e));
    }
};

window.showAddBotToRoom = async function() {
    var list = document.getElementById('add-bot-to-room-list');
    if (!list) return;
    if (list.style.display !== 'none') {
        list.style.display = 'none';
        return;
    }
    list.style.display = '';
    list.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:11px;padding:8px;">' + t('common.loading') + '</div>';
    try {
        var resp = await window.api('GET', '/api/bots');
        var bots = resp.bots || [];
        if (bots.length === 0) {
            list.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:11px;padding:8px;">' + t('bots.noBotsCreateHint') + '</div>';
            return;
        }
        var S = window.AppState;
        var roomId = S.currentRoom?.id;
        list.innerHTML = bots.map(function(b) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:var(--bg3);border-radius:6px;margin-bottom:4px;">' +
                '<span style="font-size:12px;"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:3px;"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>' + _escBot(b.name) + '</span>' +
                '<button class="btn btn-primary" style="font-size:11px;padding:2px 8px;" onclick="addBotToCurrentRoom(' + b.bot_id + ')">' + t('common.add') + '</button>' +
            '</div>';
        }).join('');
    } catch (e) {
        list.innerHTML = '<div style="color:var(--danger);font-size:11px;padding:8px;">' + (e.message || e) + '</div>';
    }
};

window.addBotToCurrentRoom = async function(botId) {
    var S = window.AppState;
    var roomId = S.currentRoom?.id;
    if (!roomId) return;
    try {
        await window.api('POST', '/api/bots/' + botId + '/rooms/' + roomId);
        window.showToast?.(t('bots.addedToRoom'), 'success');
        document.getElementById('add-bot-to-room-list').style.display = 'none';
    } catch (e) {
        window.vxAlert(t('bots.error') + ': ' + (e.message || e));
    }
};

window.editBotCommands = async function(botId) {
    var cmdsJson = await window.vxPrompt(
        t('bots.enterCommandsJson'),
        '', '[]'
    );
    if (cmdsJson === null) return;
    if (cmdsJson.trim() === '') cmdsJson = '[]';
    try {
        JSON.parse(cmdsJson);
    } catch {
        window.vxAlert(t('bots.invalidJson'));
        return;
    }
    window.api('PUT', '/api/bots/' + botId, { commands: cmdsJson })
        .then(function() { window.loadMyBots(); })
        .catch(function(e) { window.vxAlert(t('bots.error') + ': ' + (e.message || e)); });
};

// ══════════════════════════════════════════════════════════════════════════════
// Mini App — Save URL for a bot
// ══════════════════════════════════════════════════════════════════════════════

window.saveBotMiniAppUrl = async function(botId) {
    var input = document.getElementById('miniapp-url-' + botId);
    if (!input) return;
    var url = input.value.trim();
    try {
        await window.api('PUT', '/api/bots/' + botId, { mini_app_url: url });
        window.loadMyBots();
    } catch (e) {
        alert(t('bots.error') + ': ' + (e.message || e));
    }
};

window.testBotMiniApp = function(botId, url, title) {
    window.openMiniApp(botId, url, title || 'Mini App');
};

// ══════════════════════════════════════════════════════════════════════════════
// Mini App Bridge — postMessage communication between Vortex and mini app iframe
//
// PROTOCOL (for bot/mini-app developers):
//
// 1. When a mini app is opened, the iframe URL receives query parameters:
//    ?user_id=<id>&username=<username>&display_name=<name>&theme=<dark|light>&bot_id=<id>
//
// 2. The parent (Vortex) sends an init event via postMessage after iframe loads:
//    { type: "vortex_init", user_id, username, display_name, theme, accent_color, bot_id }
//
// 3. The mini app can send messages to Vortex via window.parent.postMessage():
//    { type: "close" }                              — close the mini app
//    { type: "send_message", room_id, text }        — send a message to a room
//    { type: "get_user" }                           — request current user info
//    { type: "set_title", title }                   — change the header title
//    { type: "expand" }                             — toggle fullscreen
//    { type: "haptic", style }                      — trigger haptic feedback (vibrate)
//    { type: "ready" }                              — mini app finished loading
//
// 4. Vortex responds to get_user with:
//    { type: "user_info", user_id, username, display_name, theme }
//
// ══════════════════════════════════════════════════════════════════════════════

(function() {
    var _miniAppState = {
        botId: null,
        url: null,
        title: null,
        expanded: false,
    };

    window.openMiniApp = function(botId, url, title) {
        if (!url) {
            alert(t('bots.noMiniAppUrl'));
            return;
        }

        var panel = document.getElementById('miniapp-panel');
        var frame = document.getElementById('miniapp-frame');
        var titleEl = document.getElementById('miniapp-title');
        var loading = document.getElementById('miniapp-loading');

        if (!panel || !frame) return;

        _miniAppState.botId = botId;
        _miniAppState.url = url;
        _miniAppState.title = title || 'Mini App';
        _miniAppState.expanded = false;

        titleEl.textContent = _miniAppState.title;

        panel.classList.add('show');
        loading.style.display = '';
        frame.style.display = 'none';

        var S = window.AppState;
        var user = S ? S.user : null;
        var theme = document.body.getAttribute('data-theme') || 'dark';
        var separator = url.includes('?') ? '&' : '?';
        var iframeUrl = url + separator +
            'user_id=' + encodeURIComponent(user ? user.id : '') +
            '&username=' + encodeURIComponent(user ? user.username : '') +
            '&display_name=' + encodeURIComponent(user ? (user.display_name || user.username) : '') +
            '&theme=' + encodeURIComponent(theme) +
            '&bot_id=' + encodeURIComponent(botId);

        frame.src = iframeUrl;

        frame.onload = function() {
            loading.style.display = 'none';
            frame.style.display = '';
            try {
                frame.contentWindow.postMessage({
                    type: 'vortex_init',
                    user_id: user ? user.id : null,
                    username: user ? user.username : null,
                    display_name: user ? (user.display_name || user.username) : null,
                    theme: theme,
                    accent_color: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),
                    bot_id: botId,
                }, '*');
            } catch (e) {
                console.warn('Mini App: could not send init message:', e);
            }
        };

        setTimeout(function() {
            if (loading.style.display !== 'none') {
                loading.innerHTML = '<div style="color:var(--red);font-size:13px;">Failed to load Mini App</div>' +
                    '<button class="btn btn-secondary" onclick="closeMiniApp()" style="margin-top:8px;">Close</button>';
            }
        }, 15000);
    };

    window.closeMiniApp = function() {
        var panel = document.getElementById('miniapp-panel');
        var frame = document.getElementById('miniapp-frame');
        var loading = document.getElementById('miniapp-loading');

        if (panel) panel.classList.remove('show');
        if (frame) {
            frame.src = 'about:blank';
            frame.style.display = 'none';
        }
        if (loading) {
            loading.style.display = 'none';
            loading.innerHTML = '<div class="spinner"></div><span>Loading Mini App...</span>';
        }

        _miniAppState.botId = null;
        _miniAppState.url = null;
        _miniAppState.title = null;
        _miniAppState.expanded = false;
    };

    window.toggleMiniAppExpand = function() {
        var header = document.querySelector('.miniapp-header');
        if (!header) return;
        _miniAppState.expanded = !_miniAppState.expanded;
        header.style.display = _miniAppState.expanded ? 'none' : '';
    };

    window.addEventListener('message', function(event) {
        var frame = document.getElementById('miniapp-frame');
        if (!frame || !frame.contentWindow) return;
        if (event.source !== frame.contentWindow) return;

        var data = event.data;
        if (!data || typeof data !== 'object' || !data.type) return;

        switch (data.type) {
            case 'close':
                window.closeMiniApp();
                break;

            case 'send_message':
                if (data.room_id && data.text) {
                    window.api('POST', '/api/bot/send', {
                        room_id: data.room_id,
                        text: data.text,
                    }).catch(function(e) {
                        console.warn('Mini App send_message failed:', e);
                    });
                }
                break;

            case 'get_user':
                var S = window.AppState;
                var user = S ? S.user : null;
                try {
                    frame.contentWindow.postMessage({
                        type: 'user_info',
                        user_id: user ? user.id : null,
                        username: user ? user.username : null,
                        display_name: user ? (user.display_name || user.username) : null,
                        theme: document.body.getAttribute('data-theme') || 'dark',
                    }, '*');
                } catch (e) {
                    console.warn('Mini App: could not reply to get_user:', e);
                }
                break;

            case 'set_title':
                if (data.title) {
                    var titleEl = document.getElementById('miniapp-title');
                    if (titleEl) titleEl.textContent = data.title;
                }
                break;

            case 'expand':
                window.toggleMiniAppExpand();
                break;

            case 'haptic':
                if (navigator.vibrate) {
                    var patterns = {
                        light: [10],
                        medium: [30],
                        heavy: [50],
                        success: [10, 50, 10],
                        warning: [30, 30, 30],
                        error: [50, 50, 50],
                    };
                    navigator.vibrate(patterns[data.style] || [10]);
                }
                break;

            case 'ready':
                var loadingEl = document.getElementById('miniapp-loading');
                if (loadingEl) loadingEl.style.display = 'none';
                if (frame) frame.style.display = '';
                break;

            default:
                console.warn('Mini App: unknown message type:', data.type);
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var panel = document.getElementById('miniapp-panel');
            if (panel && panel.classList.contains('show')) {
                window.closeMiniApp();
                e.preventDefault();
                e.stopPropagation();
            }
        }
    });
})();

// ══════════════════════════════════════════════════════════════════════════════
// Bot Marketplace: publish toggle from bot settings
// ══════════════════════════════════════════════════════════════════════════════

window.toggleBotPublish = async function(botId, isPublic, category) {
    try {
        await window.api('POST', '/api/bots/' + botId + '/publish', {
            is_public: isPublic,
            category: category || 'other'
        });
        window.loadMyBots();
    } catch (e) {
        alert(t('bots.error') + ': ' + (e.message || e));
    }
};

// ══════════════════════════════════════════════════════════════════════════════
// Bot Marketplace UI
// ══════════════════════════════════════════════════════════════════════════════

var _mpState = {
    category: '',
    sort: 'rating',
    searchTimeout: null,
    userRooms: []
};

function _mpCatLabel(id) {
    var keys = {
        utilities: 'bots.catUtilities',
        games: 'bots.catGames',
        moderation: 'bots.catModeration',
        music: 'bots.catMusic',
        productivity: 'bots.catProductivity',
        social: 'bots.catSocial',
        fun: 'bots.catFun',
        other: 'bots.catOther'
    };
    return keys[id] ? t(keys[id]) : id;
}

window.openMarketplace = function() {
    openModal('marketplace-modal');
    document.getElementById('mp-list-view').style.display = 'flex';
    document.getElementById('mp-detail-view').style.display = 'none';
    var searchInput = document.getElementById('mp-search');
    if (searchInput) searchInput.value = '';
    _mpState.category = '';
    _mpState.sort = 'rating';
    document.querySelectorAll('.marketplace-sort-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.sort === 'rating');
    });
    mpLoadCategories();
    mpLoadBots();
    mpLoadUserRooms();
};

window.mpLoadCategories = async function() {
    var container = document.getElementById('mp-categories');
    if (!container) return;
    try {
        var data = await window.api('GET', '/api/marketplace/categories');
        var cats = data.categories || [];
        var html = '<button class="marketplace-cat-pill active" onclick="mpSetCategory(\'\',this)">' + t('common.all') + '<span class="cat-count">' + (data.total || 0) + '</span></button>';
        cats.forEach(function(c) {
            html += '<button class="marketplace-cat-pill" onclick="mpSetCategory(\'' + c.id + '\',this)">' +
                _mpCatLabel(c.id) +
                '<span class="cat-count">' + c.count + '</span></button>';
        });
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '';
    }
};

window.mpSetCategory = function(cat, btn) {
    _mpState.category = cat;
    document.querySelectorAll('.marketplace-cat-pill').forEach(function(p) { p.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    mpLoadBots();
};

window.mpSetSort = function(sort, btn) {
    _mpState.sort = sort;
    document.querySelectorAll('.marketplace-sort-btn').forEach(function(b) { b.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    mpLoadBots();
};

window.mpSearch = function(q) {
    clearTimeout(_mpState.searchTimeout);
    _mpState.searchTimeout = setTimeout(function() {
        if (q.trim()) {
            mpSearchBots(q.trim());
        } else {
            mpLoadBots();
        }
    }, 300);
};

window.mpSearchBots = async function(q) {
    var grid = document.getElementById('mp-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="marketplace-loading">' + t('common.searching') + '</div>';
    try {
        var data = await window.api('GET', '/api/marketplace/search?q=' + encodeURIComponent(q));
        mpRenderGrid(data.bots || []);
    } catch (e) {
        grid.innerHTML = '<div class="marketplace-empty">' + t('bots.searchError') + '</div>';
    }
};

window.mpLoadBots = async function() {
    var grid = document.getElementById('mp-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="marketplace-loading">' + t('common.loading') + '</div>';
    try {
        var url = '/api/marketplace?sort=' + _mpState.sort + '&limit=50';
        if (_mpState.category) url += '&category=' + _mpState.category;
        var data = await window.api('GET', url);
        mpRenderGrid(data.bots || []);
    } catch (e) {
        grid.innerHTML = '<div class="marketplace-empty">' + t('bots.loadError') + '</div>';
    }
};

function mpRenderGrid(bots) {
    var grid = document.getElementById('mp-grid');
    if (!grid) return;
    if (bots.length === 0) {
        grid.innerHTML = '<div class="marketplace-empty" style="grid-column:1/-1;">' + t('bots.noBotsYet') + '</div>';
        return;
    }
    grid.innerHTML = bots.map(function(b) {
        var avatarHtml = b.avatar_url ?
            '<img src="' + _escBot(b.avatar_url) + '" alt="">' :
            '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>';
        return '<div class="marketplace-card" onclick="mpOpenDetail(' + b.bot_id + ')">' +
            '<div class="marketplace-card-top">' +
                '<div class="marketplace-card-avatar">' + avatarHtml + '</div>' +
                '<div class="marketplace-card-info">' +
                    '<div class="marketplace-card-name">' + _escBot(b.name) + '</div>' +
                    '<div class="marketplace-card-desc">' + _escBot(b.description) + '</div>' +
                '</div>' +
            '</div>' +
            '<div class="marketplace-card-bottom">' +
                '<div class="marketplace-card-cat">' + _mpCatLabel(b.category) + '</div>' +
                '<div class="marketplace-card-stats">' +
                    '<span class="stat-icon">' + mpStarsHtml(b.rating, true) + '</span>' +
                    '<span class="stat-icon"><svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> ' + (b.installs || 0) + '</span>' +
                '</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

function mpStarsHtml(rating, small) {
    var html = '<span class="marketplace-stars">';
    var full = Math.floor(rating);
    var half = (rating - full) >= 0.3;
    var sz = small ? '12' : '14';
    for (var i = 1; i <= 5; i++) {
        if (i <= full) {
            html += '<svg width="' + sz + '" height="' + sz + '" class="star-filled" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>';
        } else if (i === full + 1 && half) {
            html += '<svg width="' + sz + '" height="' + sz + '" class="star-half" viewBox="0 0 24 24" fill="currentColor"><path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4V6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"/></svg>';
        } else {
            html += '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 24 24" fill="currentColor"><path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"/></svg>';
        }
    }
    html += '</span>';
    return html;
}

window.mpLoadUserRooms = async function() {
    try {
        var data = await window.api('GET', '/api/rooms/my');
        _mpState.userRooms = (data.rooms || []).filter(function(r) { return r.type !== 'dm'; });
    } catch (e) {
        _mpState.userRooms = [];
    }
};

window.mpOpenDetail = async function(botId) {
    document.getElementById('mp-list-view').style.display = 'none';
    document.getElementById('mp-detail-view').style.display = 'flex';
    var content = document.getElementById('mp-detail-content');
    if (!content) return;
    content.innerHTML = '<div class="marketplace-loading">' + t('common.loading') + '</div>';

    try {
        var bot = await window.api('GET', '/api/marketplace/' + botId);
        var reviews = await window.api('GET', '/api/marketplace/' + botId + '/reviews');

        var avatarHtml = bot.avatar_url ?
            '<img src="' + _escBot(bot.avatar_url) + '" alt="">' :
            '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>';

        var cmdsHtml = '';
        var cmds = bot.commands || [];
        if (cmds.length > 0) {
            cmdsHtml = '<div class="marketplace-detail-commands"><h4>' + t('bots.commands') + '</h4>';
            cmds.forEach(function(c) {
                cmdsHtml += '<div class="marketplace-detail-cmd"><code>' + _escBot(c.command) + '</code><span>' + _escBot(c.description || '') + '</span></div>';
            });
            cmdsHtml += '</div>';
        }

        // Room selector
        var roomOptions = _mpState.userRooms.map(function(r) {
            return '<option value="' + r.id + '">' + _escBot(r.name) + '</option>';
        }).join('');
        var installHtml = roomOptions ?
            '<div class="marketplace-room-select">' +
                '<label>' + t('bots.addToRoom') + '</label>' +
                '<div style="display:flex;gap:8px;">' +
                    '<select id="mp-install-room" style="flex:1;padding:8px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;">' + roomOptions + '</select>' +
                    '<button class="btn btn-primary" onclick="mpInstallBot(' + botId + ')" style="white-space:nowrap;font-size:12px;">' + t('bots.install') + '</button>' +
                '</div>' +
            '</div>' :
            '<div style="font-size:12px;color:var(--text3);margin-bottom:16px;">' + t('bots.noRoomsForInstall') + '</div>';

        // Mini app button
        var miniAppHtml = '';
        if (bot.mini_app_url) {
            miniAppHtml = '<div style="margin-bottom:16px;">' +
                '<button class="btn btn-secondary" onclick="window.open(\'' + _escBot(bot.mini_app_url) + '\',\'_blank\')" style="font-size:12px;">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M19 19H5V5h7V3H5a2 2 0 00-2 2v14a2 2 0 002 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>' +
                    t('bots.openApp') + '</button>' +
            '</div>';
        }

        // Reviews
        var reviewsHtml = '<div class="marketplace-reviews"><h4>' + t('bots.reviews', {count: bot.rating_count || 0}) + '</h4>';

        // Review form
        var existingRating = (bot.user_review && bot.user_review.rating) || 0;
        var existingText = (bot.user_review && bot.user_review.text) || '';
        reviewsHtml += '<div class="marketplace-review-form">' +
            '<label>' + (existingRating ? t('bots.updateReview') : t('bots.leaveReview')) + '</label>' +
            '<div class="marketplace-star-input" id="mp-star-input" data-bot="' + botId + '">';
        for (var i = 1; i <= 5; i++) {
            reviewsHtml += '<span class="star' + (i <= existingRating ? ' active' : '') + '" data-val="' + i + '" onclick="mpSelectStar(this,' + i + ')">&#9733;</span>';
        }
        reviewsHtml += '</div>' +
            '<textarea id="mp-review-text" placeholder="' + t('bots.commentOptional') + '" maxlength="500">' + _escBot(existingText) + '</textarea>' +
            '<button class="btn btn-primary" onclick="mpSubmitReview(' + botId + ')" style="font-size:12px;margin-top:8px;">' + t('common.submit') + '</button>' +
        '</div>';

        // Existing reviews list
        var revList = reviews.reviews || [];
        if (revList.length > 0) {
            revList.forEach(function(r) {
                var rAvatar = r.avatar_url ?
                    '<img src="' + _escBot(r.avatar_url) + '" alt="">' :
                    '<span>' + (r.avatar_emoji || '&#x1F464;') + '</span>';
                var rDate = r.created_at ? new Date(r.created_at).toLocaleDateString('ru') : '';
                reviewsHtml += '<div class="marketplace-review-item">' +
                    '<div class="marketplace-review-avatar">' + rAvatar + '</div>' +
                    '<div class="marketplace-review-body">' +
                        '<div class="marketplace-review-top">' +
                            '<span class="marketplace-review-name">' + _escBot(r.display_name || r.username) + '</span>' +
                            '<span class="marketplace-review-date">' + rDate + '</span>' +
                        '</div>' +
                        mpStarsHtml(r.rating, true) +
                        (r.text ? '<div class="marketplace-review-text">' + _escBot(r.text) + '</div>' : '') +
                    '</div>' +
                '</div>';
            });
        } else {
            reviewsHtml += '<div style="font-size:12px;color:var(--text3);padding:8px 0;">' + t('bots.noReviewsYet') + '</div>';
        }
        reviewsHtml += '</div>';

        content.innerHTML =
            '<div class="marketplace-detail-header">' +
                '<div class="marketplace-detail-avatar">' + avatarHtml + '</div>' +
                '<div class="marketplace-detail-info">' +
                    '<div class="marketplace-detail-name">' + _escBot(bot.name) + '</div>' +
                    '<div class="marketplace-detail-owner">' + t('bots.byOwner', {name: _escBot(bot.owner_name)}) + '</div>' +
                    '<div class="marketplace-detail-stats">' +
                        '<span class="marketplace-card-cat">' + _mpCatLabel(bot.category) + '</span>' +
                        '<span>' + mpStarsHtml(bot.rating) + ' <span style="font-size:11px;color:var(--text3);">(' + (bot.rating_count || 0) + ')</span></span>' +
                        '<span><svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> ' + t('bots.installsCount', {count: bot.installs || 0}) + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            (bot.description ? '<div class="marketplace-detail-desc">' + _escBot(bot.description) + '</div>' : '') +
            cmdsHtml +
            miniAppHtml +
            installHtml +
            // Chat with bot button
            (bot.user_id ? '<div style="margin-bottom:16px;">' +
                '<button class="btn btn-primary" style="width:100%;font-size:13px;padding:10px;display:flex;align-items:center;justify-content:center;gap:8px;" onclick="mpOpenBotChat(' + bot.user_id + ')">' +
                    '<svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>' +
                    t('bots.chatWithBot') +
                '</button>' +
            '</div>' : '') +
            reviewsHtml;

    } catch (e) {
        content.innerHTML = '<div class="marketplace-empty">' + t('bots.loadError') + ': ' + _escBot(e.message || String(e)) + '</div>';
    }
};

window.mpOpenBotChat = async function(botUserId) {
    try {
        // Close marketplace/settings modals
        if (window.closeModal) {
            window.closeModal('settings-modal');
        }
        // Open DM with bot's user account
        if (window.openDM) {
            await window.openDM(botUserId);
        } else if (window.startDmWith) {
            await window.startDmWith(botUserId);
        }
    } catch (e) {
        if (window.showToast) window.showToast(t('errors.generic') + ': ' + e.message, 'error');
    }
};

window.mpBackToList = function() {
    document.getElementById('mp-list-view').style.display = 'flex';
    document.getElementById('mp-detail-view').style.display = 'none';
};

window.mpInstallBot = async function(botId) {
    try {
        // Get bot detail to find user_id
        var detail = await window.api('GET', '/api/marketplace/' + botId);
        var botUserId = detail.user_id;

        // Try install to selected room if available
        var sel = document.getElementById('mp-install-room');
        var roomId = sel ? sel.value : '';
        if (roomId) {
            await window.api('POST', '/api/marketplace/' + botId + '/install/' + roomId).catch(function() {});
        }

        if (window.showToast) window.showToast(t('bots.installedToRoom'), 'success');

        // Close settings and open DM with bot
        if (window.closeModal) window.closeModal('settings-modal');
        if (botUserId && window.openDM) {
            window.openDM(botUserId);
        } else if (botUserId && window.startDmWith) {
            window.startDmWith(botUserId);
        }
    } catch (e) {
        if (window.showToast) window.showToast(t('bots.error') + ': ' + (e.message || e), 'error');
    }
};

var _mpSelectedRating = 0;

window.mpSelectStar = function(el, val) {
    _mpSelectedRating = val;
    var container = el.parentElement;
    container.querySelectorAll('.star').forEach(function(s) {
        s.classList.toggle('active', parseInt(s.dataset.val) <= val);
    });
};

window.mpSubmitReview = async function(botId) {
    if (_mpSelectedRating < 1 || _mpSelectedRating > 5) {
        alert(t('bots.selectRating'));
        return;
    }
    var text = (document.getElementById('mp-review-text')?.value || '').trim();
    try {
        await window.api('POST', '/api/marketplace/' + botId + '/review', {
            rating: _mpSelectedRating,
            text: text
        });
        mpOpenDetail(botId);
    } catch (e) {
        alert(t('bots.error') + ': ' + (e.message || e));
    }
};

// ── Report system ──
window.showReportModal = function(userId, messageId) {
    document.getElementById('report-target-id').value = userId || '';
    document.getElementById('report-message-id').value = messageId || '';
    document.getElementById('report-reason').value = 'spam';
    document.getElementById('report-description').value = '';
    var alertEl = document.getElementById('report-alert');
    alertEl.style.display = 'none';
    alertEl.textContent = '';
    document.getElementById('report-submit-btn').disabled = false;
    document.getElementById('report-modal').classList.add('show');
};

window.submitReport = async function() {
    var targetId = document.getElementById('report-target-id').value;
    var messageId = document.getElementById('report-message-id').value;
    var reason = document.getElementById('report-reason').value;
    var description = (document.getElementById('report-description').value || '').trim();
    var alertEl = document.getElementById('report-alert');
    var submitBtn = document.getElementById('report-submit-btn');

    if (!targetId) {
        alertEl.textContent = t('report.noUserSpecified');
        alertEl.style.display = 'block';
        alertEl.style.color = '#ef4444';
        return;
    }

    submitBtn.disabled = true;
    try {
        var body = { reason: reason, description: description };
        if (messageId) body.message_id = parseInt(messageId);
        var resp = await window.api('POST', '/api/users/report/' + targetId, body);
        alertEl.textContent = resp.message || t('report.reportSent');
        alertEl.style.display = 'block';
        alertEl.style.color = '#22c55e';
        setTimeout(function() {
            document.getElementById('report-modal').classList.remove('show');
        }, 1500);
    } catch (e) {
        alertEl.textContent = e.message || t('report.reportError');
        alertEl.style.display = 'block';
        alertEl.style.color = '#ef4444';
        submitBtn.disabled = false;
    }
};

// --- end block ---
