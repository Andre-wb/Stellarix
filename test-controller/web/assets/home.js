/* Home page — populates fingerprint + stats grid. */
(() => {
    'use strict';

    let _ctrlPubkey = null;

    async function loadHealth() {
        try {
            const r = await fetch('/v1/health');
            const d = await r.json();
            _ctrlPubkey = d.pubkey;

            document.getElementById('pubkey-text').textContent = d.pubkey;
            document.getElementById('hero-status').textContent = '● online';
            document.getElementById('hero-status').className = 'badge badge-ok';
            document.getElementById('hero-version').textContent = 'v' + d.version;
            document.getElementById('foot-version').textContent = 'Vortex Controller v' + d.version;

            const s = d.stats || {};
            const grid = document.getElementById('stats-grid');
            const mkStat = (value, label) => {
                const c = document.createElement('div');
                c.className = 'stat-card';
                const v = document.createElement('div');
                v.className = 'stat-value';
                v.textContent = String(value);
                const l = document.createElement('div');
                l.className = 'stat-label';
                l.textContent = label;
                c.appendChild(v); c.appendChild(l);
                return c;
            };
            // Clear + populate
            while (grid.firstChild) grid.removeChild(grid.firstChild);
            grid.appendChild(mkStat(s.online || 0,   'peers online'));
            grid.appendChild(mkStat(s.approved || 0, 'approved'));
            grid.appendChild(mkStat(s.total || 0,    'total registered'));
        } catch (e) {
            document.getElementById('pubkey-text').textContent = 'unavailable';
            document.getElementById('hero-status').textContent = '● offline';
            document.getElementById('hero-status').className = 'badge badge-err';
        }
    }

    loadHealth();
})();
