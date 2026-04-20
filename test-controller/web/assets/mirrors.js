/* Mirrors page — signed list + health indicators. */
(() => {
    'use strict';
    let _pubkey = null;

    function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
    function mkEl(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    }

    async function init() {
        try {
            const h = await fetch('/v1/health').then(r => r.json());
            _pubkey = h.pubkey;
            document.getElementById('foot-version').textContent = 'Vortex Controller v' + h.version;
        } catch {}
        await loadMirrors();
    }

    async function loadMirrors() {
        try {
            const env = await fetch('/v1/mirrors').then(r => r.json());
            const ok = await verifyEnvelope(env, _pubkey);
            const sigEl = document.getElementById('mirrors-sig');
            if (ok === true) { sigEl.textContent = '✓ signed · verified'; sigEl.style.color = 'var(--green2)'; }
            else if (ok === false) { sigEl.textContent = '✗ bad signature'; sigEl.style.color = 'var(--red2)'; }
            else { sigEl.textContent = 'browser cannot verify'; sigEl.style.color = 'var(--yellow2)'; }

            const items = (env.payload && env.payload.mirrors) || [];
            const grid = document.getElementById('mirrors-grid');
            clear(grid);
            if (!items.length) {
                grid.appendChild(mkEl('div', 'card', 'No mirrors configured yet.'));
                return;
            }
            items.forEach(m => grid.appendChild(buildCard(m)));
        } catch {
            const grid = document.getElementById('mirrors-grid');
            clear(grid);
            grid.appendChild(mkEl('div', 'card', 'Failed to load.'));
        }
    }

    function buildCard(m) {
        const card = mkEl('div', 'item-card');

        const head = mkEl('div', 'item-head');

        let dotClass = 'dot';
        let statusText = 'not checked';
        if (m.healthy === true) { dotClass += ' dot-ok'; statusText = 'reachable' + (m.latency_ms != null ? ' · ' + m.latency_ms + 'ms' : ''); }
        else if (m.healthy === false) { dotClass += ' dot-err'; statusText = m.error || 'unreachable'; }
        else { dotClass += ' dot-warn'; }
        head.appendChild(mkEl('span', dotClass));

        const titleBox = document.createElement('div');
        titleBox.appendChild(mkEl('div', 'item-title', (m.type || 'url').toUpperCase()));
        titleBox.appendChild(mkEl('div', 'item-type', statusText));
        head.appendChild(titleBox);
        card.appendChild(head);

        card.appendChild(mkEl('code', 'item-url', m.url));

        if (m.last_checked) {
            card.appendChild(mkEl('div', 'item-desc', 'Last checked ' + ago(m.last_checked)));
        }

        const actions = mkEl('div', 'item-actions');
        const copy = mkEl('button', 'btn', 'Copy URL');
        copy.addEventListener('click', () => copyText(m.url));
        actions.appendChild(copy);
        const open = mkEl('a', 'btn');
        open.href = m.url.startsWith('ipfs://') ? 'https://ipfs.io/ipfs/' + m.url.slice(7) : m.url;
        open.target = '_blank';
        open.rel = 'noopener';
        open.textContent = 'Open';
        actions.appendChild(open);
        card.appendChild(actions);

        return card;
    }

    init();
})();
