/**
 * bot-constructor.js — Visual No-Code Bot Constructor
 * Built on top of Gravitix DSL.
 */

let _botId = null;
let _blocks = [];
let _nextBlockId = 1;
let _panel = null;

let _docsOpen = false;

const BLOCK_TYPES = [
    { type: 'command',    icon: '/',             label: function() { return t('botConstructor.command'); },        color: '#7c3aed' },
    { type: 'message',    icon: '\u{1F4AC}',     label: function() { return t('botConstructor.messagePattern'); }, color: '#3b82f6' },
    { type: 'welcome',    icon: '\u{1F44B}',     label: function() { return t('botConstructor.welcome'); },       color: '#10b981' },
    { type: 'scheduled',  icon: '\u{23F0}',      label: function() { return t('botConstructor.scheduled'); },     color: '#f59e0b' },
    { type: 'condition',  icon: '\u{2696}',      label: function() { return t('botConstructor.condition'); },     color: '#ef4444' },
    { type: 'random',     icon: '\u{1F3B2}',     label: function() { return t('botConstructor.random'); },        color: '#8b5cf6' },
    { type: 'api',        icon: '\u{1F310}',     label: function() { return t('botConstructor.apiCall'); },       color: '#06b6d4' },
    { type: 'adminNotify',icon: '\u{1F514}',     label: function() { return t('botConstructor.adminNotify'); },   color: '#f97316' },
];

window.openBotConstructor = async function(botId) {
    _botId = botId;
    _blocks = [];
    _nextBlockId = 1;
    document.getElementById('bot-constructor')?.remove();

    _panel = document.createElement('div');
    _panel.id = 'bot-constructor';
    _panel.className = 'bot-constructor';
    document.body.appendChild(_panel);

    try {
        var resp = await window.api('GET', '/api/ide/projects/' + botId);
        if (resp && resp.code) {
            _blocks = _parseGravToBlocks(resp.code);
            _nextBlockId = _blocks.length ? Math.max.apply(null, _blocks.map(function(b) { return b.id; })) + 1 : 1;
        }
    } catch (e) { /* no existing code */ }

    if (!_blocks.length) {
        _blocks.push({ id: _nextBlockId++, type: 'welcome', response: t('botConstructor.defaultWelcome') });
        _blocks.push({ id: _nextBlockId++, type: 'command', command: '/help', response: t('botConstructor.defaultHelp') });
    }
    _render();
};

window.closeBotConstructor = function() {
    _panel?.remove();
    _panel = null;
};

function _render() {
    if (!_panel) return;
    while (_panel.firstChild) _panel.removeChild(_panel.firstChild);

    // Header (safe DOM)
    var header = document.createElement('div');
    header.className = 'bc-header';

    var backBtn = document.createElement('button');
    backBtn.className = 'bc-back';
    backBtn.onclick = closeBotConstructor;
    backBtn.innerHTML = '<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>';

    var title = document.createElement('div');
    title.className = 'bc-title';
    title.innerHTML = '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>';
    var titleSpan = document.createElement('span');
    titleSpan.textContent = t('botConstructor.title');
    title.appendChild(titleSpan);

    var btnGroup = document.createElement('div');
    btnGroup.style.cssText = 'display:flex;gap:6px;';

    var docsBtn = document.createElement('button');
    docsBtn.className = 'bc-docs-btn' + (_docsOpen ? ' active' : '');
    docsBtn.onclick = function() { _docsOpen = !_docsOpen; _render(); };
    docsBtn.innerHTML = '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>';
    var docsSpan = document.createElement('span');
    docsSpan.textContent = t('botConstructor.docs');
    docsBtn.appendChild(docsSpan);

    var saveBtn = document.createElement('button');
    saveBtn.className = 'bc-save';
    saveBtn.onclick = _saveBotConstructor;
    saveBtn.innerHTML = '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>';
    var saveSpan = document.createElement('span');
    saveSpan.textContent = t('botConstructor.saveAndDeploy');
    saveBtn.appendChild(saveSpan);

    btnGroup.appendChild(docsBtn);
    btnGroup.appendChild(saveBtn);
    header.append(backBtn, title, btnGroup);
    _panel.appendChild(header);

    // Main area
    var main = document.createElement('div');
    main.className = 'bc-main';

    // Blocks
    var container = document.createElement('div');
    container.className = 'bc-blocks';
    _blocks.forEach(function(block) { container.appendChild(_renderBlock(block)); });
    main.appendChild(container);

    // Docs panel
    if (_docsOpen) {
        var docs = document.createElement('div');
        docs.className = 'bc-docs';
        docs.innerHTML = _renderDocs();
        main.appendChild(docs);
    }
    _panel.appendChild(main);

    // Add block bar — horizontal scroll
    var addBar = document.createElement('div');
    addBar.className = 'bc-add-bar';
    var label = document.createElement('div');
    label.className = 'bc-add-label';
    label.textContent = t('botConstructor.addBlock');
    addBar.appendChild(label);
    var opts = document.createElement('div');
    opts.className = 'bc-add-options';
    BLOCK_TYPES.forEach(function(bt) {
        var btn = document.createElement('button');
        btn.className = 'bc-add-btn';
        btn.style.setProperty('--bc-color', bt.color);
        btn.onclick = function() { _addBlock(bt.type); };
        btn.innerHTML = '<span class="bc-add-icon">' + bt.icon + '</span><span>' + bt.label() + '</span>';
        opts.appendChild(btn);
    });
    addBar.appendChild(opts);
    _panel.appendChild(addBar);
}

function _renderBlock(block) {
    var bt = BLOCK_TYPES.find(function(t) { return t.type === block.type; }) || BLOCK_TYPES[0];
    var el = document.createElement('div');
    el.className = 'bc-block';
    el.style.setProperty('--bc-color', bt.color);

    var trigger = '', body = '';

    if (block.type === 'command') {
        trigger = '<input class="bc-input bc-cmd" value="' + _esc(block.command || '/mycommand') + '" placeholder="/command" onchange="_updateBlock(' + block.id + ',\'command\',this.value)">';
        body = '<textarea class="bc-textarea" placeholder="' + t('botConstructor.responsePlaceholder') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>';
    } else if (block.type === 'message') {
        trigger = '<input class="bc-input" value="' + _esc(block.pattern || '') + '" placeholder="' + t('botConstructor.patternPlaceholder') + '" onchange="_updateBlock(' + block.id + ',\'pattern\',this.value)">';
        body = '<textarea class="bc-textarea" placeholder="' + t('botConstructor.responsePlaceholder') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>';
    } else if (block.type === 'welcome') {
        trigger = '<div class="bc-trigger-label">on /start</div>';
        body = '<textarea class="bc-textarea" placeholder="' + t('botConstructor.welcomeMessage') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>';
    } else if (block.type === 'condition') {
        trigger = '<input class="bc-input" value="' + _esc(block.conditionVar || 'ctx.text') + '" placeholder="Variable to check" onchange="_updateBlock(' + block.id + ',\'conditionVar\',this.value)">';
        body = '<div style="display:flex;flex-direction:column;gap:6px;">' +
            '<div style="display:flex;gap:6px;align-items:center;"><span style="color:var(--green);font-weight:600;font-size:12px;">IF TRUE</span>' +
            '<input class="bc-input" value="' + _esc(block.conditionMatch || '') + '" placeholder="' + t('botConstructor.matchValue') + '" onchange="_updateBlock(' + block.id + ',\'conditionMatch\',this.value)"></div>' +
            '<textarea class="bc-textarea" style="min-height:40px;" placeholder="' + t('botConstructor.thenResponse') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>' +
            '<div style="display:flex;gap:6px;align-items:center;"><span style="color:var(--red,#ef4444);font-weight:600;font-size:12px;">ELSE</span></div>' +
            '<textarea class="bc-textarea" style="min-height:40px;" placeholder="' + t('botConstructor.elseResponse') + '" onchange="_updateBlock(' + block.id + ',\'elseResponse\',this.value)">' + _esc(block.elseResponse || '') + '</textarea>' +
            '</div>';
    } else if (block.type === 'random') {
        trigger = '<div class="bc-trigger-label">' + t('botConstructor.randomPick') + '</div>';
        var items = block.items || [''];
        body = '<div class="bc-random-items">';
        items.forEach(function(item, i) {
            body += '<div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;">' +
                '<span style="font-size:11px;color:var(--text3);min-width:20px;">' + (i+1) + '.</span>' +
                '<input class="bc-input" value="' + _esc(item) + '" placeholder="' + t('botConstructor.randomOption') + '" onchange="_updateRandomItem(' + block.id + ',' + i + ',this.value)">' +
                (items.length > 1 ? '<button class="bc-step-del" onclick="_removeRandomItem(' + block.id + ',' + i + ')">×</button>' : '') +
                '</div>';
        });
        body += '<button class="bc-mini-btn" style="width:100%;justify-content:center;margin-top:4px;" onclick="_addRandomItem(' + block.id + ')">+ ' + t('botConstructor.addOption') + '</button></div>';
    } else if (block.type === 'api') {
        trigger = '<div style="display:flex;gap:6px;flex-wrap:wrap;">' +
            '<select class="bc-select" style="width:auto;" onchange="_updateBlock(' + block.id + ',\'method\',this.value)">' +
                '<option value="GET"' + (block.method !== 'POST' ? ' selected' : '') + '>GET</option>' +
                '<option value="POST"' + (block.method === 'POST' ? ' selected' : '') + '>POST</option></select>' +
            '<input class="bc-input" value="' + _esc(block.url || '') + '" placeholder="https://api.example.com/data" style="flex:1;" onchange="_updateBlock(' + block.id + ',\'url\',this.value)">' +
            '</div>';
        body = '<textarea class="bc-textarea" placeholder="' + t('botConstructor.apiResponseTemplate') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>';
    } else if (block.type === 'adminNotify') {
        trigger = '<div class="bc-trigger-label">' + t('botConstructor.notifyOnEvent') + '</div>';
        body = '<textarea class="bc-textarea" placeholder="' + t('botConstructor.adminMessage') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>';
    } else if (block.type === 'scheduled') {
        trigger = '<div style="display:flex;gap:8px;align-items:center;">' +
            '<span style="font-size:12px;color:var(--text2);">' + t('botConstructor.every') + '</span>' +
            '<input class="bc-input" type="number" min="1" max="999" value="' + (block.interval || 24) + '" style="width:60px;text-align:center;" onchange="_updateBlock(' + block.id + ',\'interval\',parseInt(this.value))">' +
            '<select class="bc-select" onchange="_updateBlock(' + block.id + ',\'unit\',this.value)">' +
                '<option value="hours"' + (block.unit !== 'days' ? ' selected' : '') + '>' + t('botConstructor.hours') + '</option>' +
                '<option value="days"' + (block.unit === 'days' ? ' selected' : '') + '>' + t('botConstructor.days') + '</option>' +
            '</select></div>';
        body = '<textarea class="bc-textarea" placeholder="' + t('botConstructor.scheduledMessage') + '" onchange="_updateBlock(' + block.id + ',\'response\',this.value)">' + _esc(block.response || '') + '</textarea>';
    }

    // Flow steps
    var flowHtml = '';
    if (block.type === 'command' && block.steps && block.steps.length) {
        flowHtml = '<div class="bc-flow">';
        block.steps.forEach(function(step, si) {
            flowHtml += '<div class="bc-step"><div class="bc-step-num">' + (si + 1) + '</div><div class="bc-step-body">' +
                '<input class="bc-input" value="' + _esc(step.prompt) + '" placeholder="' + t('botConstructor.askUser') + '" onchange="_updateStep(' + block.id + ',' + si + ',\'prompt\',this.value)">' +
                '<input class="bc-input bc-step-var" value="' + _esc(step.varName) + '" placeholder="' + t('botConstructor.saveAs') + '" onchange="_updateStep(' + block.id + ',' + si + ',\'varName\',this.value)">' +
                '</div><button class="bc-step-del" onclick="_removeStep(' + block.id + ',' + si + ')">×</button></div>';
        });
        flowHtml += '</div>';
    }

    var stepBtn = block.type === 'command' ? '<button class="bc-mini-btn" onclick="_addStep(' + block.id + ')" title="' + t('botConstructor.addStep') + '"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></button>' : '';

    el.innerHTML =
        '<div class="bc-block-header">' +
            '<span class="bc-block-icon" style="background:' + bt.color + '">' + bt.icon + '</span>' +
            '<span class="bc-block-type">' + bt.label() + '</span>' +
            '<div class="bc-block-actions">' + stepBtn +
                '<button class="bc-mini-btn bc-del-btn" onclick="_removeBlock(' + block.id + ')" title="' + t('app.delete') + '"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>' +
            '</div>' +
        '</div>' +
        '<div class="bc-block-trigger">' + trigger + '</div>' +
        flowHtml +
        '<div class="bc-block-body">' + body + '</div>';
    return el;
}

// Block ops
window._addBlock = function(type) {
    var block = { id: _nextBlockId++, type: type, response: '' };
    if (type === 'command') block.command = '/new';
    if (type === 'message') block.pattern = '';
    if (type === 'scheduled') { block.interval = 24; block.unit = 'hours'; }
    _blocks.push(block);
    _render();
    requestAnimationFrame(function() {
        var blocks = _panel?.querySelectorAll('.bc-block');
        if (blocks && blocks.length) blocks[blocks.length - 1].scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
};
window._removeBlock = function(id) { _blocks = _blocks.filter(function(b) { return b.id !== id; }); _render(); };
window._updateBlock = function(id, key, value) { var b = _blocks.find(function(b) { return b.id === id; }); if (b) b[key] = value; };
window._addStep = function(bid) { var b = _blocks.find(function(b) { return b.id === bid; }); if (!b) return; if (!b.steps) b.steps = []; b.steps.push({ prompt: '', varName: 'answer' }); _render(); };
window._removeStep = function(bid, si) { var b = _blocks.find(function(b) { return b.id === bid; }); if (b && b.steps) { b.steps.splice(si, 1); _render(); } };
window._updateStep = function(bid, si, key, val) { var b = _blocks.find(function(b) { return b.id === bid; }); if (b && b.steps && b.steps[si]) b.steps[si][key] = val; };

// Generate Gravitix
function _generateGravCode() {
    var code = '// Auto-generated by Vortex Bot Constructor\n\n';
    var stateVars = {};
    _blocks.forEach(function(b) { if (b.steps) b.steps.forEach(function(s) { if (s.varName) stateVars[s.varName] = true; }); });
    var varNames = Object.keys(stateVars);
    if (varNames.length) {
        code += 'state {\n';
        varNames.forEach(function(v) { code += '    ' + v + ': str = "",\n'; });
        code += '}\n\n';
    }
    _blocks.forEach(function(b) {
        if (b.type === 'welcome') {
            code += 'on /start {\n    emit "' + _escGrav(b.response) + '";\n}\n\n';
        } else if (b.type === 'command') {
            var cmd = (b.command || '/cmd').replace(/^\//, '');
            if (b.steps && b.steps.length) {
                var fn = 'flow_' + cmd;
                code += 'on /' + cmd + ' {\n    run flow ' + fn + ';\n}\n\nflow ' + fn + ' {\n';
                b.steps.forEach(function(s) {
                    code += '    emit "' + _escGrav(s.prompt) + '";\n    let ' + (s.varName || 'answer') + ' = wait msg;\n';
                });
                if (b.response) code += '    emit "' + _escGrav(b.response) + '";\n';
                code += '}\n\n';
            } else {
                code += 'on /' + cmd + ' {\n    emit "' + _escGrav(b.response) + '";\n}\n\n';
            }
        } else if (b.type === 'message') {
            code += 'on msg {\n    match ctx.text {\n        /' + (b.pattern || '.*') + '/i => emit "' + _escGrav(b.response) + '",\n        _ => {}\n    }\n}\n\n';
        } else if (b.type === 'scheduled') {
            code += 'every ' + (b.interval || 24) + ' ' + (b.unit || 'hours') + ' {\n    emit "' + _escGrav(b.response) + '";\n}\n\n';
        }
    });
    return code;
}
function _escGrav(s) { return (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n'); }

function _parseGravToBlocks(code) {
    var blocks = [];
    var m, re = /on \/(\w+)\s*\{[^}]*emit\s+"([^"]*)"[^}]*\}/g;
    while ((m = re.exec(code))) {
        blocks.push({ id: _nextBlockId++, type: m[1] === 'start' ? 'welcome' : 'command', command: '/' + m[1], response: m[2].replace(/\\n/g, '\n').replace(/\\"/g, '"') });
    }
    re = /every\s+(\d+)\s+(hours?|days?)\s*\{[^}]*emit\s+"([^"]*)"[^}]*\}/g;
    while ((m = re.exec(code))) {
        blocks.push({ id: _nextBlockId++, type: 'scheduled', interval: parseInt(m[1]), unit: m[2].replace(/s$/, '') + 's', response: m[3].replace(/\\n/g, '\n').replace(/\\"/g, '"') });
    }
    return blocks;
}

window._saveBotConstructor = async function() {
    var code = _generateGravCode();
    var saveBtn = _panel?.querySelector('.bc-save');
    if (saveBtn) { saveBtn.disabled = true; var sp = saveBtn.querySelector('span'); if (sp) sp.textContent = t('botConstructor.deploying'); }
    try {
        await window.api('PUT', '/api/bots/' + _botId, {
            commands: JSON.stringify(
                _blocks.filter(function(b) { return b.type === 'command' || b.type === 'welcome'; }).map(function(b) {
                    return {
                        command: b.type === 'welcome' ? '/start' : (b.command || '/cmd'),
                        description: (b.response || '').slice(0, 80),
                        response: b.response || '',
                    };
                })
            )
        });
        try { await window.api('POST', '/api/ide/projects/' + _botId + '/save', { code: code }); } catch (e) { /* ok */ }
        if (window.showToast) window.showToast(t('botConstructor.deployed'), 'success');
        closeBotConstructor();
    } catch (e) {
        if (window.showToast) window.showToast(t('errors.generic') + ': ' + e.message, 'error');
    } finally {
        if (saveBtn) { saveBtn.disabled = false; var sp2 = saveBtn.querySelector('span'); if (sp2) sp2.textContent = t('botConstructor.saveAndDeploy'); }
    }
};

// Random item ops
window._addRandomItem = function(bid) { var b = _blocks.find(function(b) { return b.id === bid; }); if (!b) return; if (!b.items) b.items = ['']; b.items.push(''); _render(); };
window._removeRandomItem = function(bid, i) { var b = _blocks.find(function(b) { return b.id === bid; }); if (b && b.items) { b.items.splice(i, 1); _render(); } };
window._updateRandomItem = function(bid, i, val) { var b = _blocks.find(function(b) { return b.id === bid; }); if (b && b.items) b.items[i] = val; };

// Docs
function _renderDocs() {
    return '<div class="bc-docs-inner">' +
        '<h2>' + t('botConstructor.docsTitle') + '</h2>' +

        '<h3>\u{1F4CC} ' + t('botConstructor.docsBlockTypes') + '</h3>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#7c3aed;">/ ' + t('botConstructor.command') + '</h4>' +
            '<p>' + t('botConstructor.docsCommand') + '</p>' +
            '<code>on /help { emit "Help message"; }</code>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#3b82f6;">\u{1F4AC} ' + t('botConstructor.messagePattern') + '</h4>' +
            '<p>' + t('botConstructor.docsMessage') + '</p>' +
            '<code>on msg { match ctx.text { /hello/i =&gt; emit "Hi!" } }</code>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#10b981;">\u{1F44B} ' + t('botConstructor.welcome') + '</h4>' +
            '<p>' + t('botConstructor.docsWelcome') + '</p>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#f59e0b;">\u{23F0} ' + t('botConstructor.scheduled') + '</h4>' +
            '<p>' + t('botConstructor.docsScheduled') + '</p>' +
            '<code>every 24 hours { emit "Daily reminder!"; }</code>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#ef4444;">\u{2696} ' + t('botConstructor.condition') + '</h4>' +
            '<p>' + t('botConstructor.docsCondition') + '</p>' +
            '<code>if ctx.text == "yes" { emit "Great!"; } else { emit "Maybe later"; }</code>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#8b5cf6;">\u{1F3B2} ' + t('botConstructor.random') + '</h4>' +
            '<p>' + t('botConstructor.docsRandom') + '</p>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#06b6d4;">\u{1F310} ' + t('botConstructor.apiCall') + '</h4>' +
            '<p>' + t('botConstructor.docsApi') + '</p>' +
            '<code>let data = http_get("https://api.example.com/joke");<br>emit data.joke;</code>' +
        '</div>' +

        '<div class="bc-doc-section">' +
            '<h4 style="color:#f97316;">\u{1F514} ' + t('botConstructor.adminNotify') + '</h4>' +
            '<p>' + t('botConstructor.docsAdminNotify') + '</p>' +
        '</div>' +

        '<h3>\u{1F4DD} ' + t('botConstructor.docsConversations') + '</h3>' +
        '<p>' + t('botConstructor.docsConversationsDesc') + '</p>' +
        '<code>flow register {<br>&nbsp;&nbsp;emit "What is your name?";<br>&nbsp;&nbsp;let name = wait msg;<br>&nbsp;&nbsp;emit "Hello, {name}!";<br>}</code>' +

        '<h3>\u{1F4CA} ' + t('botConstructor.docsVariables') + '</h3>' +
        '<p>' + t('botConstructor.docsVariablesDesc') + '</p>' +
        '<code>state { count: int = 0, users: map = {} }</code>' +
        '<p>' + t('botConstructor.docsBuiltinVars') + '</p>' +
        '<ul>' +
            '<li><code>{ctx.user_id}</code> — ' + t('botConstructor.docsVarUserId') + '</li>' +
            '<li><code>{ctx.first_name}</code> — ' + t('botConstructor.docsVarFirstName') + '</li>' +
            '<li><code>{ctx.text}</code> — ' + t('botConstructor.docsVarText') + '</li>' +
            '<li><code>{ctx.is_admin}</code> — ' + t('botConstructor.docsVarIsAdmin') + '</li>' +
            '<li><code>{ctx.room_id}</code> — ' + t('botConstructor.docsVarRoomId') + '</li>' +
        '</ul>' +

        '<h3>\u{1F3A8} ' + t('botConstructor.docsFormatting') + '</h3>' +
        '<p>' + t('botConstructor.docsFormattingDesc') + '</p>' +
        '<ul>' +
            '<li><code>&lt;b&gt;bold&lt;/b&gt;</code></li>' +
            '<li><code>&lt;i&gt;italic&lt;/i&gt;</code></li>' +
            '<li><code>&lt;code&gt;code&lt;/code&gt;</code></li>' +
            '<li><code>{variable}</code> — ' + t('botConstructor.docsInterpolation') + '</li>' +
        '</ul>' +

        '<h3>\u{1F527} ' + t('botConstructor.docsTips') + '</h3>' +
        '<ul>' +
            '<li>' + t('botConstructor.docsTip1') + '</li>' +
            '<li>' + t('botConstructor.docsTip2') + '</li>' +
            '<li>' + t('botConstructor.docsTip3') + '</li>' +
            '<li>' + t('botConstructor.docsTip4') + '</li>' +
            '<li>' + t('botConstructor.docsTip5') + '</li>' +
        '</ul>' +
    '</div>';
}

function _esc(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
