/* Wave 7 UI polish: theme/density toggles, command palette,
 * PiP logs window, dashboard reorder.
 *
 * Boot: wait for DOM, install global hotkey listeners, and restore
 * user preferences from localStorage. No framework — plain DOM.
 */

(() => {
    'use strict';

    const $ = sel => document.querySelector(sel);

    // ── 1. Theme + density persistence ──
    const THEME_KEY   = 'vx.theme';
    const DENSITY_KEY = 'vx.density';

    function applyTheme(t) {
        document.documentElement.setAttribute('data-theme', t);
        try { localStorage.setItem(THEME_KEY, t); } catch (_) {}
    }
    function applyDensity(d) {
        document.documentElement.setAttribute('data-density', d);
        try { localStorage.setItem(DENSITY_KEY, d); } catch (_) {}
    }
    function toggleTheme() {
        const cur = document.documentElement.getAttribute('data-theme') || 'dark';
        applyTheme(cur === 'dark' ? 'light' : 'dark');
    }
    function toggleDensity() {
        const cur = document.documentElement.getAttribute('data-density') || 'normal';
        applyDensity(cur === 'normal' ? 'compact' : 'normal');
    }
    window.vxToggleTheme   = toggleTheme;
    window.vxToggleDensity = toggleDensity;

    // Restore saved prefs
    try {
        applyTheme(localStorage.getItem(THEME_KEY)   || 'dark');
        applyDensity(localStorage.getItem(DENSITY_KEY) || 'normal');
    } catch (_) {}

    // ── 2. Command palette ──
    const COMMANDS = [
        { label: 'Toggle light / dark theme',   hint: 'Cmd+Shift+L', run: toggleTheme },
        { label: 'Toggle compact density',      hint: 'Cmd+Shift+D', run: toggleDensity },
        { label: 'Open Settings',               hint: 'G then S',    run: () => _openTab('settings') },
        { label: 'Open AI',                     hint: 'G then A',    run: () => _openTab('ai') },
        { label: 'Open Observability',          hint: 'G then O',    run: () => _openTab('observability') },
        { label: 'Open Database',               hint: 'G then D',    run: () => _openTab('database') },
        { label: 'Open Logs',                   hint: 'G then L',    run: () => _openTab('logs') },
        { label: 'Open Peers',                  hint: 'G then P',    run: () => _openTab('peers') },
        { label: 'Open Earnings',               hint: 'G then E',    run: () => _openTab('earnings') },
        { label: 'Start node',                  hint: '',            run: () => document.getElementById('btn-node-start')?.click() },
        { label: 'Stop node',                   hint: '',            run: () => document.getElementById('btn-node-stop')?.click() },
        { label: 'Rotate logs now',             hint: '',            run: () => document.getElementById('obs-logs-rotate')?.click() },
        { label: 'Upload backup now',           hint: '',            run: () => document.getElementById('btn-backup-upload')?.click() },
        { label: 'Open /metrics (Prometheus)',  hint: '',            run: () => window.open('/api/wiz/admin/metrics', '_blank') },
        { label: 'Open Swagger API docs',       hint: '',            run: () => window.open('/api/wiz/docs', '_blank') },
        { label: 'Open PiP logs',               hint: 'Cmd+Shift+P', run: openPipLogs },
    ];

    function _openTab(name) {
        const btn = document.querySelector(`.nav-item[data-tab="${name}"]`);
        if (btn) btn.click();
    }

    let palette, paletteInput, paletteList, paletteIndex = 0, paletteMatches = [];

    function buildPalette() {
        if (palette) return;
        palette = document.createElement('div');
        palette.className = 'cmd-palette';
        palette.setAttribute('role', 'dialog');
        paletteInput = document.createElement('input');
        paletteInput.placeholder = 'Type a command…';
        paletteInput.addEventListener('input', renderPalette);
        paletteInput.addEventListener('keydown', onPaletteKey);
        palette.appendChild(paletteInput);
        paletteList = document.createElement('div');
        paletteList.className = 'cmd-palette-list';
        palette.appendChild(paletteList);
        document.body.appendChild(palette);

        document.addEventListener('pointerdown', e => {
            if (palette.classList.contains('open') && !palette.contains(e.target)) closePalette();
        });
    }

    function openPalette() {
        buildPalette();
        palette.classList.add('open');
        paletteInput.value = '';
        renderPalette();
        paletteInput.focus();
    }
    function closePalette() {
        if (palette) palette.classList.remove('open');
    }
    function renderPalette() {
        const q = paletteInput.value.trim().toLowerCase();
        paletteMatches = COMMANDS.filter(c =>
            !q || c.label.toLowerCase().includes(q)
        );
        paletteIndex = 0;
        while (paletteList.firstChild) paletteList.removeChild(paletteList.firstChild);
        paletteMatches.forEach((c, i) => {
            const row = document.createElement('div');
            row.className = 'cmd-item' + (i === 0 ? ' active' : '');
            const left = document.createElement('span'); left.textContent = c.label;
            const hint = document.createElement('span'); hint.className = 'cmd-item-hint';
            hint.textContent = c.hint || '';
            row.appendChild(left); row.appendChild(hint);
            row.addEventListener('pointerdown', e => { e.preventDefault(); runMatch(i); });
            paletteList.appendChild(row);
        });
    }
    function runMatch(idx) {
        const c = paletteMatches[idx]; if (!c) return;
        closePalette();
        try { c.run(); } catch (e) { console.warn(e); }
    }
    function onPaletteKey(e) {
        if (e.key === 'Escape')    { e.preventDefault(); closePalette(); return; }
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            paletteIndex = Math.min(paletteMatches.length - 1, paletteIndex + 1);
            highlightActive();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            paletteIndex = Math.max(0, paletteIndex - 1);
            highlightActive();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            runMatch(paletteIndex);
        }
    }
    function highlightActive() {
        const rows = paletteList.querySelectorAll('.cmd-item');
        rows.forEach((r, i) => r.classList.toggle('active', i === paletteIndex));
    }
    window.vxOpenPalette = openPalette;

    // ── 3. Picture-in-Picture logs ──
    function openPipLogs() {
        let pip = document.getElementById('logs-pip');
        if (pip) { pip.style.display = 'flex'; return; }
        pip = document.createElement('div');
        pip.id = 'logs-pip';
        pip.className = 'logs-pip';
        const head = document.createElement('div'); head.className = 'logs-pip-head';
        const title = document.createElement('strong'); title.textContent = 'Node logs (live)';
        const close = document.createElement('button'); close.className = 'btn-small'; close.textContent = '✕';
        close.addEventListener('click', () => pip.style.display = 'none');
        head.appendChild(title); head.appendChild(close);
        pip.appendChild(head);
        const body = document.createElement('div'); body.className = 'logs-pip-body';
        pip.appendChild(body);
        document.body.appendChild(pip);
        // Draggable
        let dragX = 0, dragY = 0, startX = 0, startY = 0, dragging = false;
        head.addEventListener('pointerdown', e => {
            dragging = true; startX = e.clientX; startY = e.clientY;
            const r = pip.getBoundingClientRect();
            dragX = r.left; dragY = r.top;
            e.preventDefault();
        });
        window.addEventListener('pointermove', e => {
            if (!dragging) return;
            pip.style.left = (dragX + e.clientX - startX) + 'px';
            pip.style.top  = (dragY + e.clientY - startY) + 'px';
            pip.style.right = pip.style.bottom = 'auto';
        });
        window.addEventListener('pointerup', () => dragging = false);
        // Start polling logs every 3s
        const update = async () => {
            if (pip.style.display === 'none') return;
            try {
                const r = await fetch('/api/wiz/admin/logs?level=all&limit=100');
                const d = await r.json();
                body.textContent = (d.lines || []).join('\n');
                body.scrollTop = body.scrollHeight;
            } catch (_) {}
            setTimeout(update, 3000);
        };
        update();
    }
    window.vxOpenPipLogs = openPipLogs;

    // ── 4. Dashboard widget reorder ──
    // Lives inside the current panel's <header class="panel-head"> —
    // used to be fixed bottom-left but that overlapped the "Reset setup"
    // button in the sidebar foot. Panel-header placement keeps it near
    // the cards it actually reorders.
    const REORDER_KEY = 'vx.dashboardOrder';
    function initWidgetReorder() {
        const panel = document.querySelector('.panel.active');
        if (!panel) return;
        const cards = Array.from(panel.querySelectorAll(':scope > .card, :scope > .grid-2, :scope > .grid-4'));
        // Remove any stale toggle from previous panels so we don't end
        // up with duplicates when the user switches tabs.
        document.querySelectorAll('.widget-reorder-toggle').forEach(el => el.remove());
        if (cards.length < 2) return;

        const head = panel.querySelector('.panel-head .panel-head-right')
                  || panel.querySelector('.panel-head');
        if (!head) return;

        // Build the toggle DOM with explicit elements — no innerHTML, no
        // user input involved, but the linter prefers the explicit form.
        const toggle = document.createElement('button');
        toggle.className = 'widget-reorder-toggle btn-small';
        toggle.type = 'button';
        toggle.title = 'Drag cards to reorder them on this panel';
        const ns = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('width', '12');
        svg.setAttribute('height', '12');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '2.5');
        svg.setAttribute('stroke-linecap', 'round');
        svg.style.verticalAlign = '-1px';
        svg.style.marginRight = '4px';
        for (const y of [6, 12, 18]) {
            const line = document.createElementNS(ns, 'line');
            line.setAttribute('x1', '3');  line.setAttribute('y1', String(y));
            line.setAttribute('x2', '21'); line.setAttribute('y2', String(y));
            svg.appendChild(line);
        }
        toggle.appendChild(svg);
        const lbl = document.createElement('span');
        lbl.textContent = 'Reorder';
        toggle.appendChild(lbl);
        toggle.addEventListener('click', () => _reorderMode(!toggle.dataset.active));
        head.appendChild(toggle);

        // Restore saved order for this panel
        const panelId = panel.id;
        try {
            const saved = JSON.parse(localStorage.getItem(REORDER_KEY + ':' + panelId) || '[]');
            if (saved.length) _applyOrder(panel, saved);
        } catch (_) {}
    }
    function _applyOrder(panel, order) {
        const children = Array.from(panel.children);
        const byIdx = new Map(children.map((c, i) => [i, c]));
        order.forEach(i => {
            const el = byIdx.get(i);
            if (el) panel.appendChild(el);
        });
    }
    function _reorderMode(on) {
        const toggle = document.querySelector('.widget-reorder-toggle');
        if (!toggle) return;
        toggle.dataset.active = on ? '1' : '';
        // Update only the <span> label, keep the SVG icon intact.
        const lbl = toggle.querySelector('span');
        if (lbl) lbl.textContent = on ? 'Done' : 'Reorder';
        toggle.classList.toggle('active', !!on);
        const panel = document.querySelector('.panel.active');
        if (!panel) return;
        const cards = Array.from(panel.querySelectorAll(':scope > .card, :scope > .grid-2, :scope > .grid-4'));
        cards.forEach((c, i) => {
            if (on) {
                c.setAttribute('draggable', 'true');
                c.style.cursor = 'move';
                c.addEventListener('dragstart', _onDragStart);
                c.addEventListener('dragover',  _onDragOver);
                c.addEventListener('drop',      _onDrop);
                c.dataset.widgetIdx = i;
            } else {
                c.removeAttribute('draggable');
                c.style.cursor = '';
            }
        });
        if (!on) _saveOrder(panel);
    }
    function _saveOrder(panel) {
        const order = Array.from(panel.children)
            .map(c => parseInt(c.dataset.widgetIdx, 10))
            .filter(n => !isNaN(n));
        try { localStorage.setItem(REORDER_KEY + ':' + panel.id, JSON.stringify(order)); } catch (_) {}
    }
    let _dragSrc = null;
    function _onDragStart(ev) { _dragSrc = ev.currentTarget; ev.dataTransfer.effectAllowed = 'move'; }
    function _onDragOver(ev)  { ev.preventDefault(); ev.dataTransfer.dropEffect = 'move'; }
    function _onDrop(ev) {
        ev.preventDefault();
        const target = ev.currentTarget;
        if (!_dragSrc || _dragSrc === target) return;
        const parent = target.parentNode;
        const all = Array.from(parent.children);
        if (all.indexOf(_dragSrc) < all.indexOf(target)) {
            parent.insertBefore(_dragSrc, target.nextSibling);
        } else {
            parent.insertBefore(_dragSrc, target);
        }
    }
    document.addEventListener('click', e => {
        if (e.target && e.target.classList && e.target.classList.contains('nav-item')) {
            setTimeout(initWidgetReorder, 50);
        }
    });
    document.addEventListener('DOMContentLoaded', () => setTimeout(initWidgetReorder, 200));

    // ── 5. Global hotkeys ──
    window.addEventListener('keydown', e => {
        const k = (e.key || '').toLowerCase();
        const cmdOrCtrl = e.metaKey || e.ctrlKey;
        if (cmdOrCtrl && k === 'p' && !e.shiftKey && !e.altKey) {
            // Avoid fighting browser print: require Cmd+Shift+P for PiP, Cmd+K for palette
            return;
        }
        if (cmdOrCtrl && k === 'k' && !e.shiftKey) { e.preventDefault(); openPalette(); }
        if (cmdOrCtrl && e.shiftKey && k === 'l')  { e.preventDefault(); toggleTheme(); }
        if (cmdOrCtrl && e.shiftKey && k === 'd')  { e.preventDefault(); toggleDensity(); }
        if (cmdOrCtrl && e.shiftKey && k === 'p')  { e.preventDefault(); openPipLogs(); }
    });
})();
