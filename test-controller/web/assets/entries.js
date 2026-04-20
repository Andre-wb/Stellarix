/* Entries page — signed envelope + grid of cards. */
(() => {
    'use strict';
    let _pubkey = null;

    const TYPE_META = {
        tunnel: { label: 'Cloudflare Tunnel',  icon: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z"/>' },
        tor:    { label: 'Tor hidden service', icon: '<circle cx="12" cy="12" r="10"/><path d="M12 2a10 14 0 0 1 0 20M12 2a10 14 0 0 0 0 20M2 12h20"/>' },
        ipfs:   { label: 'IPFS content',       icon: '<path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="M12 2v10M3 7l9 5 9-5"/>' },
        direct: { label: 'Direct HTTPS',       icon: '<path d="M3 12h18M12 3v18"/>' },
        unknown:{ label: 'URL',                icon: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>' },
    };

    function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
    function mkEl(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    }
    function mkSvg(pathHtml) {
        const ns = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '1.8');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        // Parse safely via template
        const tmp = document.createElement('div');
        tmp.appendChild(document.createElementNS(ns, 'svg'));
        const doc = new DOMParser().parseFromString('<svg xmlns="http://www.w3.org/2000/svg">' + pathHtml + '</svg>', 'image/svg+xml');
        doc.documentElement.childNodes.forEach(n => svg.appendChild(n.cloneNode(true)));
        return svg;
    }

    async function init() {
        try {
            const h = await fetch('/v1/health').then(r => r.json());
            _pubkey = h.pubkey;
            document.getElementById('foot-version').textContent = 'Vortex Controller v' + h.version;
        } catch {}
        await loadEntries();
    }

    async function loadEntries() {
        try {
            const env = await fetch('/v1/entries').then(r => r.json());
            const ok = await verifyEnvelope(env, _pubkey);
            const sigEl = document.getElementById('entries-sig');
            if (ok === true) { sigEl.textContent = '✓ signed · verified'; sigEl.style.color = 'var(--green2)'; }
            else if (ok === false) { sigEl.textContent = '✗ signature bad — do not trust'; sigEl.style.color = 'var(--red2)'; }
            else { sigEl.textContent = 'browser cannot verify'; sigEl.style.color = 'var(--yellow2)'; }

            const items = (env.payload && env.payload.entries) || [];
            const grid = document.getElementById('entries-grid');
            clear(grid);
            if (!items.length) {
                grid.appendChild(mkEl('div', 'card', 'No entry URLs configured yet.'));
                return;
            }
            items.forEach(e => grid.appendChild(buildCard(e)));
        } catch {
            const grid = document.getElementById('entries-grid');
            clear(grid);
            grid.appendChild(mkEl('div', 'card', 'Failed to load.'));
        }
    }

    function buildCard(e) {
        const meta = TYPE_META[e.type] || TYPE_META.unknown;
        const card = mkEl('div', 'item-card');

        const head = mkEl('div', 'item-head');
        const ico = mkEl('div', 'item-ico');
        ico.appendChild(mkSvg(meta.icon));
        head.appendChild(ico);
        const titleBox = document.createElement('div');
        titleBox.appendChild(mkEl('div', 'item-title', meta.label));
        titleBox.appendChild(mkEl('div', 'item-type', e.type.toUpperCase()));
        head.appendChild(titleBox);
        card.appendChild(head);

        card.appendChild(mkEl('code', 'item-url', e.url));

        const actions = mkEl('div', 'item-actions');
        const copy = mkEl('button', 'btn');
        copy.textContent = 'Copy URL';
        copy.addEventListener('click', () => copyText(e.url));
        actions.appendChild(copy);
        card.appendChild(actions);

        return card;
    }

    init();
})();
