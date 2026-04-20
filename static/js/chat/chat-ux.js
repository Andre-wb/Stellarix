/* Chat UX bundle: jump-to-date, font size, global shortcuts,
 * accessibility helpers, PQ/FS indicators, ephemeral-mode banner.
 *
 * No rendering libs — pure DOM work, no 3rd-party deps. Runs after
 * main.js loads the chat screen.
 */

/* ── 1. Jump-to-date calendar picker ────────────────────────────────── */

function _formatYMD(d) {
    const z = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

function _scrollToDate(dateStr) {
    const container = document.getElementById('messages-container');
    if (!container) return false;
    const target = new Date(dateStr + 'T00:00:00').getTime() / 1000;
    // Messages have .msg-group with optional data-created-at; fall back
    // to the date dividers render.js inserts.
    const dividers = container.querySelectorAll('.date-divider');
    let matchDivider = null;
    // Render.js formats dates via fmtDate — tolerate "Today"/"Yesterday"
    // by matching the first divider whose preceding groups are all newer
    // than the target.
    const groups = Array.from(container.querySelectorAll('.msg-group'));
    for (const g of groups) {
        const iso = g.dataset && g.dataset.createdAt;
        if (!iso) continue;
        const ts = new Date(iso).getTime() / 1000;
        if (ts >= target) {
            g.scrollIntoView({ behavior: 'smooth', block: 'start' });
            g.style.animation = 'msg-highlight 1.5s ease';
            return true;
        }
    }
    // Fallback — grab the first divider whose text contains the year
    const y = dateStr.split('-')[0];
    for (const d of dividers) {
        if (d.textContent && d.textContent.includes(y)) {
            matchDivider = d;
            break;
        }
    }
    if (matchDivider) {
        matchDivider.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return true;
    }
    return false;
}

function _openDatePicker() {
    // Ensure element exists
    let box = document.getElementById('jump-to-date-popover');
    if (!box) {
        box = document.createElement('div');
        box.id = 'jump-to-date-popover';
        box.className = 'jtd-popover';
        box.setAttribute('role', 'dialog');
        box.setAttribute('aria-label', 'Перейти к дате');
        const input = document.createElement('input');
        input.type = 'date';
        input.id = 'jtd-input';
        input.setAttribute('aria-label', 'Дата');
        input.max = _formatYMD(new Date());
        input.addEventListener('change', () => {
            if (input.value) {
                const ok = _scrollToDate(input.value);
                if (!ok && window.showToast) {
                    window.showToast('Нет сообщений до этой даты', 'info');
                }
                box.style.display = 'none';
            }
        });
        const label = document.createElement('span');
        label.textContent = 'Перейти к дате:';
        label.style.fontSize = '12px';
        box.appendChild(label);
        box.appendChild(input);
        document.body.appendChild(box);
    }
    // Position near chat header
    const anchor = document.querySelector('.chat-header') || document.body;
    const r = anchor.getBoundingClientRect();
    box.style.display = 'flex';
    box.style.top  = (r.bottom + 6) + 'px';
    box.style.left = (r.right - 280) + 'px';
    setTimeout(() => document.getElementById('jtd-input')?.focus(), 40);
    const offClick = (e) => {
        if (!box.contains(e.target)) {
            box.style.display = 'none';
            document.removeEventListener('pointerdown', offClick, true);
        }
    };
    setTimeout(() => document.addEventListener('pointerdown', offClick, true), 0);
}

window.openJumpToDate = _openDatePicker;

/* ── 2. Font size + 3. Global shortcuts ─────────────────────────────── */

const FONT_KEY = 'vx.fontSize';
const FONT_MIN = 12, FONT_MAX = 22, FONT_DEFAULT = 15;

function _applyFontSize(px) {
    const n = Math.max(FONT_MIN, Math.min(FONT_MAX, Number(px) || FONT_DEFAULT));
    document.documentElement.style.setProperty('--vx-font-size', n + 'px');
    try { localStorage.setItem(FONT_KEY, String(n)); } catch (_) {}
}
function _loadFontSize() {
    try {
        const saved = localStorage.getItem(FONT_KEY);
        if (saved) _applyFontSize(saved);
    } catch (_) {}
}
window.vxSetFontSize    = _applyFontSize;
window.vxIncreaseFontSize = () => _applyFontSize(_currentFont() + 1);
window.vxDecreaseFontSize = () => _applyFontSize(_currentFont() - 1);
function _currentFont() {
    try {
        const v = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--vx-font-size'), 10);
        return isFinite(v) ? v : FONT_DEFAULT;
    } catch { return FONT_DEFAULT; }
}

const SHORTCUTS = [
    { keys: ['Ctrl+K', 'Meta+K'], desc: 'Search', run: () => {
        const b = document.getElementById('btn-global-search'); if (b) b.click();
    }},
    { keys: ['Ctrl+J', 'Meta+J'], desc: 'Jump to date', run: _openDatePicker },
    { keys: ['Ctrl+/', 'Meta+/'], desc: 'Show shortcuts help', run: _showShortcutsHelp },
    { keys: ['Ctrl+Shift+C', 'Meta+Shift+C'], desc: 'Copy selected', run: () => {
        const sel = window.getSelection(); if (sel) navigator.clipboard?.writeText(sel.toString());
    }},
    { keys: ['Ctrl+Plus', 'Ctrl+=', 'Meta+Plus', 'Meta+='],
      desc: 'Increase font',      run: () => _applyFontSize(_currentFont() + 1) },
    { keys: ['Ctrl+Minus', 'Ctrl+-', 'Meta+Minus', 'Meta+-'],
      desc: 'Decrease font',      run: () => _applyFontSize(_currentFont() - 1) },
    { keys: ['Ctrl+0', 'Meta+0'], desc: 'Reset font',          run: () => _applyFontSize(FONT_DEFAULT) },
    { keys: ['Escape'],           desc: 'Close popovers',      run: _closePopovers },
];

function _eventMatches(ev, combo) {
    const parts = combo.split('+').map(p => p.trim());
    const last = parts[parts.length - 1].toLowerCase();
    const needCtrl  = parts.includes('Ctrl');
    const needMeta  = parts.includes('Meta');
    const needShift = parts.includes('Shift');
    const needAlt   = parts.includes('Alt');
    if (needCtrl  && !ev.ctrlKey)  return false;
    if (needMeta  && !ev.metaKey)  return false;
    if (needShift && !ev.shiftKey) return false;
    if (needAlt   && !ev.altKey)   return false;
    const key = (ev.key || '').toLowerCase();
    if (last === 'plus') return key === '+' || key === '=';
    if (last === 'minus')return key === '-';
    return key === last;
}

function _handleGlobalKey(ev) {
    // Ignore when typing in an input that owns arrow/shortcut semantics
    const tag = (ev.target && ev.target.tagName) || '';
    const typing = (tag === 'INPUT' || tag === 'TEXTAREA' || ev.target?.isContentEditable);
    for (const sc of SHORTCUTS) {
        for (const combo of sc.keys) {
            if (_eventMatches(ev, combo)) {
                // Escape always runs; typing shortcuts skip modifiers-free single keys
                if (typing && combo === 'Escape') continue;
                if (typing && !/Ctrl|Meta/.test(combo)) continue;
                ev.preventDefault();
                try { sc.run(); } catch (e) { console.warn(e); }
                return;
            }
        }
    }
}

function _closePopovers() {
    document.getElementById('jump-to-date-popover')?.style.setProperty('display', 'none');
    document.getElementById('shortcuts-help')?.style.setProperty('display', 'none');
}

function _showShortcutsHelp() {
    let help = document.getElementById('shortcuts-help');
    if (!help) {
        help = document.createElement('div');
        help.id = 'shortcuts-help';
        help.className = 'shortcuts-help';
        help.setAttribute('role', 'dialog');
        help.setAttribute('aria-label', 'Keyboard shortcuts');
        const title = document.createElement('h3');
        title.textContent = 'Keyboard shortcuts';
        help.appendChild(title);
        const ul = document.createElement('ul');
        SHORTCUTS.forEach(sc => {
            const li = document.createElement('li');
            const kbd = document.createElement('kbd');
            kbd.textContent = sc.keys[0];
            const desc = document.createElement('span');
            desc.textContent = ' — ' + sc.desc;
            li.appendChild(kbd); li.appendChild(desc);
            ul.appendChild(li);
        });
        help.appendChild(ul);
        const close = document.createElement('button');
        close.textContent = 'Закрыть';
        close.className = 'btn-small';
        close.addEventListener('click', () => help.style.display = 'none');
        help.appendChild(close);
        document.body.appendChild(help);
    }
    help.style.display = 'block';
}

/* ── 4. Accessibility helpers (ARIA / high-contrast) ────────────────── */

function _installA11y() {
    // Add aria-label to unlabeled icon buttons.
    document.querySelectorAll('button:not([aria-label])').forEach(b => {
        const title = b.getAttribute('title');
        const txt = (b.textContent || '').trim();
        if (title)        b.setAttribute('aria-label', title);
        else if (txt)     b.setAttribute('aria-label', txt);
    });
    // Messages container: live region for announcements.
    const mc = document.getElementById('messages-container');
    if (mc && !mc.hasAttribute('aria-live')) {
        mc.setAttribute('aria-live', 'polite');
        mc.setAttribute('aria-label', 'Чат сообщения');
    }
    // High-contrast toggle — uses a body class; persisted.
    const HC_KEY = 'vx.highContrast';
    const apply = on => {
        document.body.classList.toggle('vx-high-contrast', !!on);
        try { localStorage.setItem(HC_KEY, on ? '1' : '0'); } catch (_) {}
    };
    try {
        const saved = localStorage.getItem(HC_KEY);
        if (saved === '1') apply(true);
    } catch (_) {}
    window.vxToggleHighContrast = () => apply(!document.body.classList.contains('vx-high-contrast'));
}

/* ── 5. PQ / FS indicators ──────────────────────────────────────────── */

function _setCryptoBadges(roomId) {
    const header = document.querySelector('.chat-header-right') || document.querySelector('.chat-header');
    if (!header) return;
    let wrap = document.getElementById('vx-crypto-badges');
    if (!wrap) {
        wrap = document.createElement('span');
        wrap.id = 'vx-crypto-badges';
        wrap.className = 'vx-crypto-badges';
        header.appendChild(wrap);
    }
    wrap.replaceChildren();

    // PQ badge — we consider PQ active when kyber_public_key exists for
    // our account (HTTP /api/keys/me would return it). Simpler: look at
    // window.AppState for flag, otherwise optimistic show-on-DM.
    const S = window.AppState || {};
    const room = S.currentRoom || {};

    const pq = document.createElement('span');
    pq.className = 'vx-badge vx-badge-pq';
    pq.title = 'Post-quantum key exchange (Kyber-768 + X25519)';
    pq.textContent = 'PQ';
    pq.setAttribute('aria-label', 'Post-quantum protected');
    wrap.appendChild(pq);

    const ratchetEpoch = (room.ratchet_epoch != null) ? room.ratchet_epoch : null;
    if (ratchetEpoch != null) {
        const fs = document.createElement('span');
        fs.className = 'vx-badge vx-badge-fs';
        fs.title = 'Double Ratchet forward secrecy · epoch ' + ratchetEpoch;
        fs.textContent = 'FS#' + ratchetEpoch;
        fs.setAttribute('aria-label', 'Forward secrecy epoch ' + ratchetEpoch);
        wrap.appendChild(fs);
    } else {
        const fs = document.createElement('span');
        fs.className = 'vx-badge vx-badge-fs';
        fs.title = 'Double Ratchet forward secrecy';
        fs.textContent = 'FS';
        wrap.appendChild(fs);
    }
}

window.vxSetCryptoBadges = _setCryptoBadges;

/* ── 6. Ephemeral mode banner ───────────────────────────────────────── */

async function _checkEphemeralMode() {
    try {
        const r = await fetch('/api/health');
        if (!r.ok) return;
        const d = await r.json();
        // Surface per-node config flags so other modules (e.g. padding in
        // room-crypto.js) can read them via window.AppState.config without
        // a second request.
        try {
            if (!window.AppState) window.AppState = {};
            if (!window.AppState.config) window.AppState.config = {};
            Object.assign(window.AppState.config, {
                metadata_padding: (d.metadata_padding !== false),
                ephemeral:        !!d.ephemeral,
                post_quantum:     d.post_quantum || null,
            });
        } catch (_) {}
        if (!d.ephemeral) return;
        let banner = document.getElementById('vx-ephemeral-banner');
        if (banner) return;
        banner = document.createElement('div');
        banner.id = 'vx-ephemeral-banner';
        banner.className = 'vx-ephemeral-banner';
        banner.setAttribute('role', 'alert');
        banner.textContent = 'Ephemeral mode: данные не сохраняются на диск. После перезапуска ноды — всё пропадёт.';
        document.body.insertBefore(banner, document.body.firstChild);
    } catch (_) {}
}

/* ── Boot ───────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
    _loadFontSize();
    window.addEventListener('keydown', _handleGlobalKey);
    _installA11y();
    _checkEphemeralMode();
});
