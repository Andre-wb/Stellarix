/* Nodes page — fetch, verify, filter, render node rows. */
(() => {
    'use strict';

    let _pubkey = null;
    let _peers = [];
    let _filter = 'all';

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
        await loadPeers();
    }

    async function loadPeers() {
        try {
            const r = await fetch('/v1/nodes/random?count=32');
            const env = await r.json();
            const ok = await verifyEnvelope(env, _pubkey);
            const warn = (ok === false);
            _peers = (env.payload && env.payload.nodes) || [];
            render(warn);
        } catch {
            const host = document.getElementById('nodes-list');
            clear(host);
            host.appendChild(mkEl('div', 'card', 'Failed to load.'));
        }
    }

    function classify(peer) {
        const sealed = !!(peer.sealed || peer.code_hash || (peer.metadata && peer.metadata.sealed));
        if (sealed) return 'dual';
        if (peer.weight != null) return 'ctrl';
        return 'warn';
    }

    function weightClass(w) {
        if (w == null) return '';
        if (w >= 0.6) return '';
        if (w >= 0.3) return 'low';
        return 'gone';
    }

    function render(sigWarn) {
        const host = document.getElementById('nodes-list');
        clear(host);

        if (sigWarn) {
            const w = mkEl('div', 'card',
                '⚠ signature verification failed — showing data anyway but do not trust without cross-check');
            w.style.borderColor = 'rgba(239,68,68,0.4)';
            host.appendChild(w);
        }

        let shown = 0;
        _peers.forEach(p => {
            const klass = classify(p);
            const w = p.weight ?? 0;
            if (_filter === 'dual'  && klass !== 'dual') return;
            if (_filter === 'ctrl'  && klass !== 'ctrl') return;
            if (_filter === 'fresh' && w < 0.8) return;
            if (_filter === 'stale' && w >= 0.5) return;
            host.appendChild(buildRow(p, klass));
            shown++;
        });
        if (shown === 0) {
            host.appendChild(mkEl('div', 'card', 'No nodes match this filter.'));
        }
    }

    function buildRow(p, klass) {
        const row = mkEl('div', 'node-row');
        const top = mkEl('div', 'node-row-top');

        const freshSec = Date.now() / 1000 - p.last_seen;
        const dotClass = freshSec < 300 ? 'dot-ok' : freshSec < 3600 ? 'dot-warn' : 'dot-err';
        top.appendChild(mkEl('span', 'dot ' + dotClass));

        top.appendChild(mkEl('span', 'node-name',
            (p.metadata && p.metadata.name) || 'unnamed'));
        top.appendChild(mkEl('code', 'node-pubkey', shortKey(p.pubkey, 8)));

        const right = mkEl('div', 'node-right');

        const tag = document.createElement('span');
        if (klass === 'dual') { tag.className = 'badge badge-ok'; tag.textContent = '✓✓ DUAL'; }
        else if (klass === 'ctrl') { tag.className = 'badge badge-info'; tag.textContent = '✓ CTRL'; }
        else { tag.className = 'badge badge-warn'; tag.textContent = '⚠ UNVERIF'; }
        right.appendChild(tag);

        const wrap = mkEl('span', 'weight-bar');
        const track = mkEl('span', 'weight-track');
        const fill = mkEl('span', 'weight-fill ' + weightClass(p.weight));
        fill.style.width = Math.round((p.weight ?? 0) * 100) + '%';
        track.appendChild(fill);
        wrap.appendChild(track);
        wrap.appendChild(mkEl('span', 'weight-num', (p.weight ?? 0).toFixed(2)));
        right.appendChild(wrap);

        const agoEl = mkEl('span', '', ago(p.last_seen));
        agoEl.style.fontSize = '11px';
        agoEl.style.color = 'var(--text3)';
        right.appendChild(agoEl);

        top.appendChild(right);
        row.appendChild(top);

        const meta = mkEl('div', 'node-meta');
        const addMeta = (label, value) => {
            const d = document.createElement('div');
            d.appendChild(mkEl('span', '', label));
            d.appendChild(mkEl('span', '', value));
            meta.appendChild(d);
        };
        if (p.metadata && p.metadata.region) addMeta('region', p.metadata.region);
        if (p.metadata && p.metadata.version) addMeta('version', p.metadata.version);
        if (p.sealed || p.code_hash) addMeta('code hash', p.code_hash ? shortKey(p.code_hash, 6) : 'sealed');
        if (meta.childElementCount > 0) row.appendChild(meta);

        if (p.endpoints && p.endpoints.length) {
            const eps = mkEl('div', 'node-endpoints');
            p.endpoints.forEach(ep => eps.appendChild(mkEl('div', 'endpoint', ep)));
            row.appendChild(eps);
        }
        return row;
    }

    document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
        document.querySelectorAll('.chip').forEach(x => x.classList.toggle('active', x === c));
        _filter = c.dataset.filter;
        render(false);
    }));

    init();
})();
