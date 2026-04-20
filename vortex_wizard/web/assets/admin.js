/* Vortex Admin Dashboard — local-only SPA
 *
 * Polls /api/wiz/admin/* every 5s. Zero outbound traffic. Every DOM write
 * uses safe DOM methods (createElement / textContent) — no innerHTML on
 * anything that came from an API.
 */

(() => {
    'use strict';

    const POLL_INTERVAL_MS = 5000;

    const $ = sel => document.querySelector(sel);

    // ── DOM helpers ────────────────────────────────────────────────────
    function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

    function td(text, className) {
        const el = document.createElement('td');
        if (className) el.className = className;
        el.textContent = text ?? '';
        return el;
    }

    function toast(msg, ms) {
        const t = $('#toast');
        t.textContent = msg;
        t.classList.add('show');
        setTimeout(() => t.classList.remove('show'), ms || 1800);
    }

    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            toast('Copied');
        } catch {
            const ta = document.createElement('textarea');
            ta.value = text; document.body.appendChild(ta); ta.select();
            document.execCommand('copy'); ta.remove(); toast('Copied');
        }
    }

    // ── Tab switching ──────────────────────────────────────────────────
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b === btn));
            document.querySelectorAll('.panel').forEach(p => {
                p.classList.toggle('active', p.id === 'panel-' + tab);
            });
            if (tab === 'logs') {
                loadLogs();
                _startLogsAutoRefresh();
            } else {
                _stopLogsAutoRefresh();
            }
            if (tab === 'earnings') loadEarnings();
            if (tab === 'database') loadDbStatus();
            if (tab === 'traffic')  loadTraffic();  // also redraws graphs
            if (tab === 'observability') loadObservability();
            if (tab === 'settings')      loadSettings();
            if (tab === 'ai')            loadAiStatus();
        });
    });

    // ── Logs tab auto-refresh ────────────────────────────────────────
    // Only ticks while the Logs tab is actually visible, so we don't
    // burn cycles when the user is elsewhere.
    let _logsTimer = null;
    function _startLogsAutoRefresh() {
        if (_logsTimer) return;
        _logsTimer = setInterval(() => {
            if (document.hidden) return;           // tab in background
            const panel = document.getElementById('panel-logs');
            if (!panel || !panel.classList.contains('active')) {
                _stopLogsAutoRefresh();
                return;
            }
            loadLogs();
        }, 3000);
    }
    function _stopLogsAutoRefresh() {
        if (_logsTimer) {
            clearInterval(_logsTimer);
            _logsTimer = null;
        }
    }

    // Generic [data-copy="#selector"] handler for copy buttons (used by the
    // Earnings panel wallet address button, among others).
    document.querySelectorAll('[data-copy]').forEach(btn => {
        btn.addEventListener('click', () => {
            const sel = btn.getAttribute('data-copy');
            const target = sel ? document.querySelector(sel) : null;
            const text = (target && target.textContent || '').trim();
            if (text && text !== '—') copyText(text);
        });
    });

    // ── 1. Whole-repo integrity (wraps scripts/integrity_repo.py) ─────
    async function loadRepoIntegrity() {
        try {
            const d = await fetch('/api/wiz/admin/repo-integrity/status').then(r => r.json());
            renderRepoIntegrity({
                // Quick status view before the first sign/verify; shows
                // whether a manifest exists and its metadata.
                status: d.has_manifest ? 'signed' : 'no_manifest',
                matched: d.file_count ?? '—',
                pubkey: d.pubkey,
                version: d.version,
                built_at: d.built_at,
            });
        } catch (e) {
            renderRepoIntegrity({ status: 'unknown', message: String(e) });
        }
    }

    async function repoSign() {
        const btn = $('#btn-repo-sign');
        const prev = btn ? btn.textContent : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="vx-spin"></span> Signing…'; }
        try {
            const r = await fetch('/api/wiz/admin/repo-integrity/sign', { method: 'POST' });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const d = await r.json();
            renderRepoIntegrity({
                status: 'verified',
                matched: d.files,
                pubkey: d.pubkey,
                built_at: d.built_at,
                version: null,
                message: `Signed ${d.files} files in ${d.duration_s}s`,
            });
            toast(`✓ Repo signed — ${d.files} files (${d.duration_s}s)`, 4000);
        } catch (e) {
            renderRepoIntegrity({ status: 'unknown', message: String(e) });
            toast(`Sign failed: ${e}`, 3500);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = prev; }
        }
    }

    async function repoVerify() {
        const btn = $('#btn-repo-verify');
        const prev = btn ? btn.textContent : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="vx-spin"></span> Verifying…'; }
        try {
            const r = await fetch('/api/wiz/admin/repo-integrity/verify', { method: 'POST' });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const d = await r.json();
            renderRepoIntegrity(d);
            const msg = (d.status === 'verified')
                ? `✓ ${d.matched}/${d.total} files match signed manifest`
                : d.status === 'tampered'
                    ? `⚠ ${(d.mismatched || []).length} file(s) differ`
                    : d.status === 'no_manifest'
                        ? 'No signed manifest yet — click "Sign repo" first'
                        : `Status: ${d.status}`;
            toast(msg, 4000);
        } catch (e) {
            renderRepoIntegrity({ status: 'unknown', message: String(e) });
            toast(`Verify failed: ${e}`, 3500);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = prev; }
        }
    }

    function renderRepoIntegrity(d) {
        const badge = $('#repo-integrity-badge');
        const badgeClasses = { verified: 'ok', signed: 'ok', tampered: 'err',
            bad_signature: 'err', no_manifest: 'warn', unknown: 'warn' };
        if (badge) {
            badge.className = 'card-badge ' + (badgeClasses[d.status] || 'warn');
            badge.textContent = d.status || '?';
        }
        if (d.matched !== undefined) {
            $('#repo-integrity-matched').textContent = d.matched ?? '—';
        }
        if (d.message) $('#repo-integrity-message').textContent = d.message;
        $('#repo-integrity-pubkey').textContent = (d.pubkey || '—').slice(0, 32) +
            (d.pubkey && d.pubkey.length > 32 ? '…' : '');
        $('#repo-integrity-version').textContent = d.version ?? '—';
        $('#repo-integrity-built-at').textContent = d.built_at
            ? new Date(d.built_at * 1000).toLocaleString() : '—';
        const bad = (d.mismatched?.length || 0) + (d.missing?.length || 0);
        $('#repo-integrity-mismatched').textContent =
            bad || (d.extra?.length ? d.extra.length + ' extra' : '0');

        const diffCard = $('#repo-integrity-diff');
        const diffList = $('#repo-integrity-diff-list');
        if (diffCard && diffList) {
            clear(diffList);
            const all = [
                ...(d.mismatched || []),
                ...(d.missing || []).map(p => '[MISSING] ' + p),
            ];
            if (all.length) {
                diffCard.style.display = '';
                all.slice(0, 100).forEach(p => {
                    const li = document.createElement('li');
                    li.textContent = p;
                    diffList.appendChild(li);
                });
                if (all.length > 100) {
                    const li = document.createElement('li');
                    li.textContent = `… +${all.length - 100} more`;
                    li.style.opacity = '0.6';
                    diffList.appendChild(li);
                }
            } else {
                diffCard.style.display = 'none';
            }
        }
    }

    // ── 2. Identity ───────────────────────────────────────────────────
    async function loadIdentity() {
        const [id, ov] = await Promise.all([
            fetch('/api/wiz/admin/identity').then(r => r.json()),
            fetch('/api/wiz/admin/overview').then(r => r.json()),
        ]);
        $('#identity-pubkey').textContent = id.pubkey || id.message || '—';
        $('#identity-device').textContent = ov.device_name || '—';
        $('#identity-mode').textContent = ov.network_mode || '—';
        $('#identity-registered').textContent = ov.running ? 'Yes' : 'No';
        // On-chain seal — from migration-hint metadata if available
        const hint = ov.migration_hint || {};
        const selfPub = (hint.node?.pubkey || '').toLowerCase();
        $('#identity-sealed').textContent = '—';
        $('#identity-code-hash').textContent = '—';
        $('#identity-checkin').textContent = '—';

        // Public URL the wizard produced (cloudflared tunnel / manual
        // announce URL). Prefer the *live* tunnel URL from the node
        // controller — it's fresher than whatever's in .env and reflects
        // the current cloudflared session.
        let nodeStatus = null;
        try { nodeStatus = await fetch('/api/wiz/admin/node/status').then(r => r.json()); }
        catch (_) { nodeStatus = null; }
        const liveTunnel = (nodeStatus && nodeStatus.tunnel_url) || '';
        const primary = (liveTunnel || ov.announce_url || '').trim();
        const all     = Array.isArray(ov.announce_all) ? ov.announce_all : [];
        const card    = document.getElementById('identity-announce-card');
        const code    = document.getElementById('identity-announce');
        const open    = document.getElementById('identity-announce-open');
        const extra   = document.getElementById('identity-announce-extra');
        if (primary) {
            if (card) card.style.display = '';
            if (code) code.textContent = primary;
            if (open) {
                open.href = primary;
                open.style.display = primary.startsWith('http') ? '' : 'none';
            }
            if (extra) {
                // Populate the list of *additional* announce URLs (rare
                // case: operator set several comma-separated URLs).
                while (extra.firstChild) extra.removeChild(extra.firstChild);
                const rest = all.slice(1);
                if (rest.length === 0) {
                    extra.style.display = 'none';
                } else {
                    rest.forEach(u => {
                        const li = document.createElement('li');
                        li.textContent = u;
                        extra.appendChild(li);
                    });
                    extra.style.display = '';
                }
            }
        } else if (card) {
            card.style.display = 'none';
        }
    }

    // ── 3. Controller ─────────────────────────────────────────────────
    async function loadController() {
        const ov = await fetch('/api/wiz/admin/overview').then(r => r.json());
        $('#ctrl-url').textContent = ov.controller_url || '—';
        $('#ctrl-pubkey').textContent = ov.controller_pubkey || '—';
        $('#ctrl-last-sig').textContent = ov.running ? 'just now' : '—';
        $('#ctrl-sns').textContent = ov.controller_url ? 'check manually' : '—';

        const fb = $('#ctrl-fallbacks');
        clear(fb);
        const env = await fetch('/api/wiz/admin/env').then(r => r.json());
        const raw = env.CONTROLLER_FALLBACK_URLS || '';
        const items = raw.split(',').map(s => s.trim()).filter(Boolean);
        if (!items.length) {
            const p = document.createElement('span');
            p.className = 'card-desc';
            p.textContent = 'None configured';
            fb.appendChild(p);
        } else {
            items.forEach(u => {
                const r = document.createElement('div');
                r.className = 'card-row';
                const s = document.createElement('span');
                s.textContent = u;
                const tag = document.createElement('span');
                tag.className = 'verify-tag ctrl';
                tag.textContent = 'configured';
                r.appendChild(s); r.appendChild(tag);
                fb.appendChild(r);
            });
        }
    }

    // ── 4. Peers ──────────────────────────────────────────────────────
    async function loadPeers() {
        const d = await fetch('/api/wiz/admin/peers').then(r => r.json());
        const tbody = $('#peers-tbody');
        clear(tbody);
        const peers = d.peers || [];
        $('#peers-count').textContent = peers.length + ' peer' + (peers.length === 1 ? '' : 's');
        if (!peers.length) {
            const row = document.createElement('tr');
            const cell = td('No peers visible', 'empty');
            cell.colSpan = 5;
            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }
        peers.forEach(p => {
            const tr = document.createElement('tr');
            tr.appendChild(td((p.pubkey || '').slice(0, 16) + '…'));
            tr.appendChild(td(p.verification || 'unknown'));
            const vtd = document.createElement('td');
            const tag = document.createElement('span');
            const vtype = (p.metadata?.sealed || p.verification === 'solana+controller')
                ? 'solana' : 'ctrl';
            tag.className = 'verify-tag ' + vtype;
            tag.textContent = vtype === 'solana' ? '✓✓ dual' : '✓ ctrl';
            vtd.appendChild(tag);
            tr.appendChild(vtd);
            tr.appendChild(td((p.weight ?? 1.0).toFixed(2)));
            const age = p.last_seen ? Math.round((Date.now() / 1000 - p.last_seen) / 60) : '—';
            tr.appendChild(td(typeof age === 'number' ? age + ' min ago' : age));
            tbody.appendChild(tr);
        });
    }

    // ── 5. Traffic ────────────────────────────────────────────────────
    // Rolling 2-minute window, one sample per poll tick. Kept in-memory,
    // never sent anywhere. Old samples drop off the left as new ones arrive.
    const TRAFFIC_BUF_MAX = 24;  // ≈ 2 min at 5s poll
    const _trafficBuf = { cpu: [], mem: [], ws: [], rooms: [] };

    async function loadTraffic() {
        const d = await fetch('/api/wiz/admin/traffic').then(r => r.json());
        const ws = d.ws_active ?? 0;
        const rooms = d.rooms_active ?? 0;
        const mem = d.memory_mb ?? 0;
        const cpu = d.cpu_seconds ?? 0;
        $('#traffic-ws').textContent = ws;
        $('#traffic-rooms').textContent = rooms;
        $('#traffic-mem').textContent = mem + ' MB';
        $('#traffic-cpu').textContent = Number(cpu).toFixed(1) + ' s';

        // Append to rolling buffer regardless of tab visibility, so when the
        // user switches in, they see the last 2 min.
        _pushTraffic(_trafficBuf.cpu,   cpu);
        _pushTraffic(_trafficBuf.mem,   mem);
        _pushTraffic(_trafficBuf.ws,    ws);
        _pushTraffic(_trafficBuf.rooms, rooms);

        // Only bother drawing when the Traffic tab is actually visible.
        const panel = document.getElementById('panel-traffic');
        if (panel && panel.classList.contains('active')) {
            _renderGraph('#g-cpu',   _trafficBuf.cpu,   '#8b5cf6');
            _renderGraph('#g-mem',   _trafficBuf.mem,   '#60a5fa');
            _renderGraph('#g-ws',    _trafficBuf.ws,    '#34d399');
            _renderGraph('#g-rooms', _trafficBuf.rooms, '#f59e0b');
        }
    }

    function _pushTraffic(arr, v) {
        arr.push(typeof v === 'number' ? v : Number(v) || 0);
        while (arr.length > TRAFFIC_BUF_MAX) arr.shift();
    }

    // Render a polyline + latest-value label into an existing <svg>.
    function _renderGraph(sel, values, color) {
        const svg = document.querySelector(sel);
        if (!svg) return;
        const W = 600, H = 80, PAD = 4;
        while (svg.firstChild) svg.removeChild(svg.firstChild);

        if (!values.length) return;

        const max = Math.max(...values);
        const min = Math.min(...values);
        const span = max - min || 1;
        const stepX = values.length > 1 ? (W - PAD * 2) / (values.length - 1) : 0;

        // Grid lines (horizontal, quartile)
        const ns = 'http://www.w3.org/2000/svg';
        for (let i = 0; i <= 3; i++) {
            const y = PAD + ((H - PAD * 2) * i) / 3;
            const line = document.createElementNS(ns, 'line');
            line.setAttribute('x1', PAD);
            line.setAttribute('x2', W - PAD);
            line.setAttribute('y1', y);
            line.setAttribute('y2', y);
            line.setAttribute('stroke', 'rgba(255,255,255,0.05)');
            line.setAttribute('stroke-width', '1');
            svg.appendChild(line);
        }

        // Build path points
        const pts = values.map((v, i) => {
            const x = PAD + stepX * i;
            const y = H - PAD - ((v - min) / span) * (H - PAD * 2);
            return [x, y];
        });

        // Fill area under the line for better visual density
        const areaD = 'M' + pts.map(p => p.join(',')).join(' L') +
                      ` L${PAD + stepX * (values.length - 1)},${H - PAD} L${PAD},${H - PAD} Z`;
        const area = document.createElementNS(ns, 'path');
        area.setAttribute('d', areaD);
        area.setAttribute('fill', color);
        area.setAttribute('fill-opacity', '0.12');
        svg.appendChild(area);

        // Main polyline
        const line = document.createElementNS(ns, 'polyline');
        line.setAttribute('points', pts.map(p => p.join(',')).join(' '));
        line.setAttribute('fill', 'none');
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', '1.5');
        line.setAttribute('stroke-linejoin', 'round');
        svg.appendChild(line);

        // Latest-value dot
        const last = pts[pts.length - 1];
        const dot = document.createElementNS(ns, 'circle');
        dot.setAttribute('cx', last[0]);
        dot.setAttribute('cy', last[1]);
        dot.setAttribute('r', '2.5');
        dot.setAttribute('fill', color);
        svg.appendChild(dot);

        // Min/max labels in the corners so users see the axis scale
        const txtMax = document.createElementNS(ns, 'text');
        txtMax.setAttribute('x', W - PAD);
        txtMax.setAttribute('y', PAD + 10);
        txtMax.setAttribute('text-anchor', 'end');
        txtMax.setAttribute('fill', 'rgba(255,255,255,0.45)');
        txtMax.setAttribute('font-size', '10');
        txtMax.textContent = _fmtMetric(max);
        svg.appendChild(txtMax);

        const txtMin = document.createElementNS(ns, 'text');
        txtMin.setAttribute('x', W - PAD);
        txtMin.setAttribute('y', H - PAD);
        txtMin.setAttribute('text-anchor', 'end');
        txtMin.setAttribute('fill', 'rgba(255,255,255,0.45)');
        txtMin.setAttribute('font-size', '10');
        txtMin.textContent = _fmtMetric(min);
        svg.appendChild(txtMin);
    }

    function _fmtMetric(v) {
        if (v == null || isNaN(v)) return '—';
        if (v >= 100) return Math.round(v).toString();
        if (v >= 10)  return v.toFixed(1);
        return v.toFixed(2);
    }

    // ── 6. Certs & Keys ───────────────────────────────────────────────
    async function loadCerts() {
        const d = await fetch('/api/wiz/admin/certs').then(r => r.json());
        const ssl = d.ssl || {};
        $('#cert-subject').textContent = ssl.subject || '—';
        $('#cert-expiry').textContent = ssl.not_after
            ? new Date(ssl.not_after * 1000).toLocaleString() : '—';
        $('#cert-days').textContent = ssl.days_left != null ? ssl.days_left + ' days' : '—';
        $('#keys-jwt-age').textContent = d.jwt_secret_age_days != null
            ? d.jwt_secret_age_days + ' days' : '—';
        $('#keys-csrf-age').textContent = d.csrf_secret_age_days != null
            ? d.csrf_secret_age_days + ' days' : '—';
    }

    // ── 7. Logs ───────────────────────────────────────────────────────
    async function loadLogs() {
        const level = $('#logs-filter').value;
        const d = await fetch('/api/wiz/admin/logs?level=' + encodeURIComponent(level)).then(r => r.json());
        const out = $('#logs-output');
        out.textContent = (d.lines || []).join('\n') || '(no logs available)';
        out.scrollTop = out.scrollHeight;
    }

    // ── Node status (footer) ──────────────────────────────────────────
    async function loadNodeStatus() {
        try {
            const d = await fetch('/api/wiz/admin/node/status').then(r => r.json());
            const reachable = !!d.http_reachable;
            const alive = !!d.process_alive;
            // 3 possible sidebar states:
            //   reachable         → fully up (green)
            //   alive, !reachable → booting / crashed listener (amber)
            //   neither           → offline (red)
            let cls = 'err', label = 'node offline';
            if (reachable)   { cls = 'ok';   label = 'node online'; }
            else if (alive)  { cls = 'warn'; label = 'node booting…'; }
            $('#node-dot').className = 'status-dot ' + cls;
            $('#node-status').textContent = label;

            // Show the live tunnel URL only when the NODE itself is up.
            // Otherwise the URL is either stale (the tunnel is from an
            // earlier session) or irrelevant — showing it gives the
            // misleading impression that the node is reachable when it
            // isn't.
            const versionEl = $('#node-version');
            while (versionEl.firstChild) versionEl.removeChild(versionEl.firstChild);
            const publicUrl = d.tunnel_url || '';
            const localUrl  = d.url || '';
            if (alive && publicUrl) {
                const a = document.createElement('a');
                a.href = publicUrl;
                a.target = '_blank';
                a.rel = 'noopener';
                a.textContent = publicUrl;
                a.title = 'Public URL (click to open) · local: ' + localUrl;
                a.style.color = '#a78bfa';
                versionEl.appendChild(a);
            } else if (alive && !reachable) {
                versionEl.textContent = 'tunnel starting…';
            } else {
                // Node offline — don't display anything misleading, just
                // the configured bind address so the user can see what
                // would go live when they click Start.
                versionEl.textContent = localUrl;
                versionEl.style.opacity = '0.5';
                return;
            }
            versionEl.style.opacity = '1';

            // Reveal the matching control button.
            const startBtn = $('#btn-node-start');
            const stopBtn  = $('#btn-node-stop');
            if (alive) {
                startBtn.style.display = 'none';
                stopBtn.style.display = '';
            } else {
                startBtn.style.display = '';
                stopBtn.style.display = 'none';
                startBtn.disabled = false;
                startBtn.textContent = 'Start node';
            }
        } catch {
            $('#node-dot').className = 'status-dot err';
            $('#node-status').textContent = 'error';
        }
    }

    async function startNode() {
        const btn = $('#btn-node-start');
        btn.disabled = true;
        btn.textContent = 'Starting…';
        try {
            const r = await fetch('/api/wiz/admin/node/start', { method: 'POST' });
            // Read body as text first — some errors return plain-text or
            // HTML, and calling .json() on those would throw the opaque
            // SyntaxError the user was seeing.
            const text = await r.text();
            let d = null;
            try { d = JSON.parse(text); } catch { /* leave d null */ }

            if (!r.ok) {
                // Port already in use — surface a calm, 5s warning. We
                // deliberately do NOT kill the other process; user
                // decides how to handle it (close their app, change PORT
                // in .env, or wait).
                if (r.status === 409 && d && d.detail && d.detail.error === 'port_in_use') {
                    const h = d.detail;
                    const who = (h.holder && h.holder.command) || 'another process';
                    const msg = `Port ${h.port} is already in use by ${who}`
                              + (h.holder && h.holder.pid ? ` (PID ${h.holder.pid})` : '')
                              + '. Close it or change PORT in .env.';
                    toast(msg, 5000);
                    console.warn('[node/start]', h);
                } else {
                    const msg = (d && (d.detail || d.error))
                             || ('HTTP ' + r.status + ': ' + text.slice(0, 200));
                    toast(msg);
                    console.error('[node/start]', r.status, text);
                }
                btn.disabled = false;
                btn.textContent = 'Start node';
                return;
            }
            if (!d) {
                toast('Bad response: ' + text.slice(0, 160));
                console.error('[node/start] non-JSON', r.status, text);
                btn.disabled = false;
                btn.textContent = 'Start node';
                return;
            }
            let msg = 'node pid ' + d.pid + (d.already_running ? ' (already running)' : '');
            if (d.tunnel_pending) msg += ' · tunnel starting…';
            if (d.tunnel_error)   msg += ' · ' + d.tunnel_error;
            toast(msg);

            // Keep refreshing the footer label + button state on its own
            // cadence — it reads /node/status which already knows about
            // both the child process and the tunnel.
            loadNodeStatus();
            setTimeout(loadNodeStatus, 1200);
            setTimeout(loadNodeStatus, 3000);
            setTimeout(loadIdentity, 1500);

            // If a tunnel is coming up, poll until its URL appears and
            // update the Identity "Public URL" card when it does.
            if (d.tunnel_pending) {
                let tries = 0;
                const poll = setInterval(async () => {
                    tries++;
                    try {
                        const s = await fetch('/api/wiz/admin/node/status').then(r => r.json());
                        // Refresh sidebar button on every tick too
                        loadNodeStatus();
                        if (s.tunnel_url) {
                            clearInterval(poll);
                            toast('public: ' + s.tunnel_url);
                            loadIdentity();
                        }
                    } catch (_) {}
                    if (tries > 30) clearInterval(poll);  // give up after ~60s
                }, 2000);
            }
        } catch (e) {
            toast(String(e));
            btn.disabled = false;
            btn.textContent = 'Start node';
        }
        // Poll status shortly after so the label flips to "booting/online".
        setTimeout(loadNodeStatus, 800);
    }

    async function stopNode() {
        const btn = $('#btn-node-stop');
        btn.disabled = true;
        btn.textContent = 'Stopping…';
        try {
            await fetch('/api/wiz/admin/node/stop', { method: 'POST' });
            toast('node stopped');
        } catch (e) {
            toast(String(e));
        }
        btn.disabled = false;
        btn.textContent = 'Stop';
        setTimeout(loadNodeStatus, 300);
    }

    $('#btn-node-start').addEventListener('click', startNode);
    $('#btn-node-stop') .addEventListener('click', stopNode);

    // ── Reset setup (wipes .env + keys → back to Setup UI on reload) ──
    $('#btn-reset-setup').addEventListener('click', async () => {
        const msg = 'Delete node identity + config? You will return to '
                  + 'the setup flow. Chat history (vortex.db) is kept.';
        if (!confirm(msg)) return;
        const btn = $('#btn-reset-setup');
        btn.disabled = true;
        btn.textContent = 'Resetting…';
        try {
            const r = await fetch('/api/wiz/admin/reset', { method: 'POST' });
            if (!r.ok) {
                const err = await r.text();
                toast('reset failed: ' + err.slice(0, 120));
                btn.disabled = false;
                btn.textContent = 'Reset setup';
                return;
            }
            toast('Reset done — returning to setup…');
            // The server's _current_mode() now resolves to 'setup' because
            // the env file is gone. A full reload picks that up.
            setTimeout(() => location.reload(), 500);
        } catch (e) {
            toast('reset failed: ' + e);
            btn.disabled = false;
            btn.textContent = 'Reset setup';
        }
    });

    // ── Earnings ──────────────────────────────────────────────────────
    async function loadEarnings() {
        try {
            const r = await fetch('/api/wiz/admin/earnings');
            const d = await r.json();
            $('#earn-wallet').textContent      = d.wallet_pubkey || '—';
            $('#earn-monthly-sol').textContent = (d.estimated?.monthly_sol ?? 0);
            $('#earn-monthly-usd').textContent = (d.estimated?.monthly_usd ?? 0).toLocaleString();
            $('#earn-uptime').textContent      = d.uptime_pct ?? '—';
            $('#earn-users').textContent       = d.users_served ?? '—';
            $('#earn-stake').textContent       = d.stake_sol ?? 0;
            $('#earn-regfee').textContent      = d.register_fee_paid ? '✓ paid' : '— not yet';
            // Premium operator bonus indicator
            const badge = $('#earn-premium-badge');
            if (badge) {
                if (d.premium && d.premium.active) {
                    badge.style.display = '';
                    badge.textContent = 'PREMIUM ×' + (d.premium.multiplier || 1.2);
                } else {
                    badge.style.display = 'none';
                }
            }
            if (d.note) {
                $('#earn-note-text').textContent = d.note;
                $('#earn-note').style.display = '';
            }
        } catch (e) {
            $('#earn-wallet').textContent = 'error loading';
        }
    }

    // ── Database (embedded PostgreSQL) ────────────────────────────────
    function _dbMsg(text, ok) {
        const el = $('#db-msg');
        el.textContent = text || '';
        el.className = 'alert ' + (text ? (ok ? 'alert-ok show' : 'alert-err show') : '');
    }

    async function loadDbStatus() {
        try {
            const d = await fetch('/api/wiz/admin/db/status').then(r => r.json());
            $('#db-current').textContent    = d.env_uses_postgres ? 'PostgreSQL' : 'SQLite (default)';
            $('#db-installed').textContent  = d.installed ? '✓ ' + (d.pg_ctl || '') : '— (will brew install on setup)';
            $('#db-cluster').textContent    = d.cluster_inited ? '✓ ' + d.pgdata : '—';
            $('#db-running').textContent    = d.running ? '✓ online' : '— stopped';
            $('#db-pgdata').textContent     = d.pgdata || '—';

            const hasCluster = !!d.cluster_inited;
            $('#btn-db-start').style.display     = hasCluster && !d.running ? '' : 'none';
            $('#btn-db-stop').style.display      = hasCluster &&  d.running ? '' : 'none';
            $('#btn-db-uninstall').style.display = hasCluster ? '' : 'none';
        } catch (e) {
            _dbMsg('Status error: ' + e, false);
        }
    }

    $('#btn-db-setup').addEventListener('click', async () => {
        const pw = ($('#db-password').value || '').trim();
        if (pw.length < 8) { _dbMsg('Password must be at least 8 chars', false); return; }
        const btn = $('#btn-db-setup');
        btn.disabled = true;
        btn.textContent = 'Setting up… (can take a few min on first install)';
        _dbMsg('Installing + initialising — please wait', true);
        try {
            const r = await fetch('/api/wiz/admin/db/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pw, port: 0 }),
            });
            const txt = await r.text();
            let d = null; try { d = JSON.parse(txt); } catch {}
            if (!r.ok) {
                _dbMsg('Failed: ' + ((d && d.detail) || txt.slice(0, 200)), false);
            } else {
                _dbMsg(`PostgreSQL ready on port ${d.port}. Restart the node to switch over.`, true);
                $('#db-password').value = '';
                await loadDbStatus();
            }
        } catch (e) {
            _dbMsg('Error: ' + e, false);
        }
        btn.disabled = false;
        btn.textContent = 'Set up PostgreSQL';
    });

    $('#btn-db-start').addEventListener('click', async () => {
        _dbMsg('starting…', true);
        try {
            const r = await fetch('/api/wiz/admin/db/start', { method: 'POST' });
            const d = await r.json();
            if (!r.ok) { _dbMsg(d.detail || 'start failed', false); return; }
            _dbMsg('started', true);
            await loadDbStatus();
        } catch (e) { _dbMsg(String(e), false); }
    });

    $('#btn-db-stop').addEventListener('click', async () => {
        _dbMsg('stopping…', true);
        try {
            const r = await fetch('/api/wiz/admin/db/stop', { method: 'POST' });
            const d = await r.json();
            if (!r.ok) { _dbMsg(d.detail || 'stop failed', false); return; }
            _dbMsg('stopped', true);
            await loadDbStatus();
        } catch (e) { _dbMsg(String(e), false); }
    });

    // ── DB viewer ─────────────────────────────────────────────────────
    const _dbView = { table: null, offset: 0, limit: 50 };

    async function loadDbTables() {
        const tbody = $('#db-tables-tbody');
        const summary = $('#db-tables-summary');
        clear(tbody);
        try {
            const r = await fetch('/api/wiz/admin/db/tables');
            const d = await r.json();
            if (!r.ok) {
                const row = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 4; td.className = 'empty';
                td.textContent = d.detail || 'error loading tables';
                row.appendChild(td); tbody.appendChild(row);
                return;
            }
            const kindLabel = d.kind === 'postgres'
                ? `PostgreSQL @ ${d.host}:${d.port}/${d.database}`
                : `SQLite · ${d.path || '—'}`;
            const sizeLabel = d.total_bytes != null
                ? ` · total ${_fmtBytes(d.total_bytes)}` : '';
            summary.textContent = kindLabel + sizeLabel + ` · ${d.tables.length} tables`;

            if (!d.tables.length) {
                const row = document.createElement('tr');
                const tdd = document.createElement('td');
                tdd.colSpan = 4; tdd.className = 'empty';
                tdd.textContent = d.note || 'no tables yet';
                row.appendChild(tdd); tbody.appendChild(row);
                return;
            }
            d.tables.forEach(t => {
                const row = document.createElement('tr');
                row.appendChild(td(t.name));
                row.appendChild(td(String(t.rows)));
                row.appendChild(td(t.bytes != null ? _fmtBytes(t.bytes) : '—'));
                const actionTd = document.createElement('td');
                const btn = document.createElement('button');
                btn.className = 'btn-small';
                btn.textContent = 'View';
                btn.addEventListener('click', () => {
                    _dbView.table = t.name; _dbView.offset = 0;
                    loadDbRows();
                });
                actionTd.appendChild(btn);
                row.appendChild(actionTd);
                tbody.appendChild(row);
            });
        } catch (e) {
            summary.textContent = 'error: ' + e;
        }
    }

    async function loadDbRows() {
        const card = $('#db-rows-card');
        const thead = $('#db-rows-thead');
        const tbody = $('#db-rows-tbody');
        const title = $('#db-rows-title');
        const hint  = $('#db-rows-hint');
        card.style.display = '';
        clear(thead); clear(tbody);
        title.textContent = _dbView.table;
        hint.textContent = 'loading…';
        try {
            const qs = '?limit=' + _dbView.limit + '&offset=' + _dbView.offset;
            const r = await fetch('/api/wiz/admin/db/table/'
                + encodeURIComponent(_dbView.table) + qs);
            const d = await r.json();
            if (!r.ok) { hint.textContent = d.detail || 'error'; return; }
            hint.textContent = `${_dbView.offset + 1}–${Math.min(_dbView.offset + d.rows.length, d.total)} of ${d.total}`;

            const htr = document.createElement('tr');
            d.columns.forEach(c => { const th = document.createElement('th'); th.textContent = c; htr.appendChild(th); });
            thead.appendChild(htr);

            d.rows.forEach(rowVals => {
                const tr = document.createElement('tr');
                rowVals.forEach(v => tr.appendChild(td(v)));
                tbody.appendChild(tr);
            });
        } catch (e) {
            hint.textContent = 'error: ' + e;
        }
    }

    $('#db-rows-prev').addEventListener('click', () => {
        _dbView.offset = Math.max(0, _dbView.offset - _dbView.limit);
        loadDbRows();
    });
    $('#db-rows-next').addEventListener('click', () => {
        _dbView.offset += _dbView.limit;
        loadDbRows();
    });
    $('#db-rows-close').addEventListener('click', () => {
        $('#db-rows-card').style.display = 'none';
    });

    function _fmtBytes(n) {
        if (n == null) return '—';
        const u = ['B','KB','MB','GB','TB'];
        let i = 0; let v = n;
        while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
        return v.toFixed(v >= 10 || i === 0 ? 0 : 1) + ' ' + u[i];
    }

    // Load tables whenever the Database tab is opened.
    const _origLoadDbStatus = loadDbStatus;
    loadDbStatus = async function() {
        await _origLoadDbStatus();
        loadDbTables();
        loadBackupStatus();
    };

    // ── Encrypted backup ─────────────────────────────────────────────
    function _backupMsg(text, ok) {
        const el = $('#backup-msg');
        if (!el) return;
        el.textContent = text || '';
        el.className = 'alert ' + (text ? (ok ? 'alert-ok show' : 'alert-err show') : '');
    }

    async function loadBackupStatus() {
        try {
            const r = await fetch('/api/wiz/admin/backup/status');
            const d = await r.json();
            const localSize = d.database_exists
                ? _fmtBytes(d.database_byte_size || 0) + ' · ' + (d.database_path || '—')
                : '— нет файла';
            $('#backup-local').textContent = localSize;
            if (!d.supported) {
                $('#backup-remote').textContent = 'не поддерживается для ' + d.database_backend;
                ['btn-backup-upload','btn-backup-restore','btn-backup-delete'].forEach(id => {
                    const b = $('#'+id); if (b) b.disabled = true;
                });
                return;
            }
            ['btn-backup-upload','btn-backup-restore','btn-backup-delete'].forEach(id => {
                const b = $('#'+id); if (b) b.disabled = false;
            });
            if (!d.controller_url) {
                $('#backup-remote').textContent = '— CONTROLLER_URL не задан';
                return;
            }
            if (d.controller_error) {
                $('#backup-remote').textContent = 'ошибка: ' + d.controller_error;
                return;
            }
            if (d.remote_exists) {
                $('#backup-remote').textContent = '✓ ' + _fmtBytes(d.remote_byte_size || 0);
                $('#backup-updated').textContent = d.remote_updated_at
                    ? new Date(d.remote_updated_at * 1000).toLocaleString()
                    : '—';
                $('#backup-sha').textContent = d.remote_sha256 || '—';
            } else {
                $('#backup-remote').textContent = '— ещё не загружен';
                $('#backup-updated').textContent = '—';
                $('#backup-sha').textContent = '—';
            }
        } catch (e) {
            _backupMsg('Ошибка статуса: ' + e, false);
        }
    }

    $('#btn-backup-upload')?.addEventListener('click', async () => {
        const btn = $('#btn-backup-upload');
        btn.disabled = true;
        const origText = btn.textContent;
        btn.textContent = 'Загрузка…';
        _backupMsg('Снимок БД → шифрование → загрузка (локально, не из памяти ноды)…', true);
        try {
            const r = await fetch('/api/wiz/admin/backup/upload', { method: 'POST' });
            const txt = await r.text();
            let d = null; try { d = JSON.parse(txt); } catch {}
            if (!r.ok) {
                _backupMsg('Ошибка: ' + ((d && d.detail) || txt.slice(0, 200)), false);
            } else {
                _backupMsg(
                    `Готово — ${_fmtBytes(d.byte_size)} зашифрованного blob'а на контроллере (исходник ${_fmtBytes(d.plaintext_byte_size)}).`,
                    true);
                await loadBackupStatus();
            }
        } catch (e) { _backupMsg(String(e), false); }
        btn.disabled = false;
        btn.textContent = origText;
    });

    $('#btn-backup-restore')?.addEventListener('click', async () => {
        if (!confirm('Восстановить БД с контроллера? Текущий локальный vortex.db будет переименован в vortex.db.pre-restore.bak, а его место займёт копия с контроллера.\n\nНода должна быть остановлена.')) return;
        const btn = $('#btn-backup-restore');
        btn.disabled = true;
        const origText = btn.textContent;
        btn.textContent = 'Восстановление…';
        _backupMsg('Скачивание blob\'а → проверка подписи → расшифровка → запись файла…', true);
        try {
            const r = await fetch('/api/wiz/admin/backup/restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: true }),
            });
            const txt = await r.text();
            let d = null; try { d = JSON.parse(txt); } catch {}
            if (!r.ok) {
                _backupMsg('Ошибка: ' + ((d && d.detail) || txt.slice(0, 200)), false);
            } else {
                _backupMsg(
                    `Восстановлено в ${d.restored_to} (${_fmtBytes(d.plaintext_byte_size)}). Запусти ноду.`,
                    true);
                await loadBackupStatus();
            }
        } catch (e) { _backupMsg(String(e), false); }
        btn.disabled = false;
        btn.textContent = origText;
    });

    $('#btn-backup-delete')?.addEventListener('click', async () => {
        if (!confirm('Удалить бэкап с контроллера? Это НЕ трогает локальный файл. Отменить нельзя.')) return;
        _backupMsg('Удаление…', true);
        try {
            const r = await fetch('/api/wiz/admin/backup/delete', { method: 'POST' });
            const d = await r.json();
            if (!r.ok) { _backupMsg('Ошибка: ' + (d.detail || r.status), false); return; }
            _backupMsg('Удалено с контроллера.', true);
            await loadBackupStatus();
        } catch (e) { _backupMsg(String(e), false); }
    });

    $('#btn-db-uninstall').addEventListener('click', async () => {
        if (!confirm('Stop the cluster, wipe pgdata, and revert to SQLite? Chat history stored in PostgreSQL will be lost.')) return;
        _dbMsg('uninstalling…', true);
        try {
            const r = await fetch('/api/wiz/admin/db/uninstall', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: true, remove_cluster: true }),
            });
            const d = await r.json();
            if (!r.ok) { _dbMsg(d.detail || 'uninstall failed', false); return; }
            _dbMsg('Cluster removed. Restart the node to use SQLite again.', true);
            await loadDbStatus();
        } catch (e) { _dbMsg(String(e), false); }
    });

    // ── Bind actions ──────────────────────────────────────────────────
    $('#btn-repo-sign').addEventListener('click', repoSign);
    $('#btn-repo-verify').addEventListener('click', repoVerify);
    $('#btn-copy-pubkey').addEventListener('click', () => {
        const t = $('#identity-pubkey').textContent || '';
        if (t && t !== '—') copyText(t);
    });
    $('#btn-refresh-logs').addEventListener('click', loadLogs);
    $('#logs-filter').addEventListener('change', loadLogs);
    $('#btn-copy-logs').addEventListener('click', () => {
        copyText($('#logs-output').textContent || '');
    });

    // ── Observability: audit + profiler + log rotation/search ─────────
    async function loadObservability() {
        loadAuditEntries();
        loadProfiler();
        loadLogFiles();
        loadOpsJobs();
        loadOpsUptime();
        loadOpsVersion();
        loadSecurity();
    }

    function _secMsg(text, ok) {
        const el = $('#sec-msg'); if (!el) return;
        el.textContent = text || '';
        el.className = 'alert ' + (text ? (ok ? 'alert-ok show' : 'alert-err show') : '');
    }

    async function loadSecurity() {
        try {
            const t = await fetch('/api/wiz/admin/sec/totp/status').then(r => r.json());
            const el = $('#sec-totp-status');
            if (el) el.textContent = t.enabled ? '✓ включено' : '— выключено';
            $('#btn-sec-totp-setup').style.display = t.enabled ? 'none' : '';
            $('#btn-sec-totp-disable').style.display = t.enabled ? '' : 'none';
        } catch {}
        try {
            const p = await fetch('/api/wiz/admin/sec/passphrase/status').then(r => r.json());
            const el = $('#sec-pass-status');
            if (el) el.textContent = p.missing ? '— нет ключа' :
                (p.enabled ? (p.locked ? '🔒 заперт' : '✓ разблокирован') : '— не защищён');
            $('#btn-sec-pass-enable').style.display = (!p.missing && !p.enabled) ? '' : 'none';
            $('#btn-sec-pass-unlock').style.display = (p.enabled && p.locked) ? '' : 'none';
        } catch {}
        try {
            const h = await fetch('/api/wiz/admin/sec/headers').then(r => r.json());
            $('#sec-csp-profile').value = h.csp_profile || 'strict';
            $('#sec-hsts-profile').value = h.hsts_profile || 'off';
        } catch {}
    }

    $('#btn-sec-totp-setup')?.addEventListener('click', async () => {
        try {
            const r = await fetch('/api/wiz/admin/sec/totp/init', { method: 'POST' });
            const d = await r.json();
            if (!r.ok) { _secMsg(d.detail || 'init failed', false); return; }
            const code = prompt(
                'Отсканируй QR в authenticator-приложении:\n\n' + d.uri +
                '\n\nВведи 6-значный код чтобы подтвердить.');
            if (!code) return;
            const cr = await fetch('/api/wiz/admin/sec/totp/confirm', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ code: code.trim() }),
            });
            const cd = await cr.json();
            if (!cr.ok) { _secMsg(cd.detail || 'confirm failed', false); return; }
            _secMsg('2FA включено — сессия действует 12 часов', true);
            loadSecurity();
        } catch (e) { _secMsg(String(e), false); }
    });

    $('#btn-sec-totp-disable')?.addEventListener('click', async () => {
        const code = prompt('Введи код TOTP чтобы выключить 2FA:');
        if (!code) return;
        const r = await fetch('/api/wiz/admin/sec/totp/disable', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ code: code.trim() }),
        });
        const d = await r.json();
        if (!r.ok) { _secMsg(d.detail || 'disable failed', false); return; }
        _secMsg('2FA выключено', true);
        loadSecurity();
    });

    $('#btn-sec-pass-enable')?.addEventListener('click', async () => {
        const p1 = prompt('Введи passphrase для шифрования ключа (>=8 символов):');
        if (!p1 || p1.length < 8) return;
        const p2 = prompt('Повтори для проверки:');
        if (p1 !== p2) { _secMsg('passphrases не совпадают', false); return; }
        const r = await fetch('/api/wiz/admin/sec/passphrase/enable', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ passphrase: p1 }),
        });
        const d = await r.json();
        if (!r.ok) { _secMsg(d.detail || 'enable failed', false); return; }
        _secMsg('Ключ зашифрован. При следующем запуске потребуется passphrase.', true);
        loadSecurity();
    });

    $('#btn-sec-pass-unlock')?.addEventListener('click', async () => {
        const p = prompt('Введи passphrase:');
        if (!p) return;
        const r = await fetch('/api/wiz/admin/sec/passphrase/unlock', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ passphrase: p }),
        });
        const d = await r.json();
        if (!r.ok) { _secMsg(d.detail || 'wrong', false); return; }
        _secMsg('Разблокировано', true);
        loadSecurity();
    });

    $('#btn-sec-headers-save')?.addEventListener('click', async () => {
        const csp  = $('#sec-csp-profile').value;
        const hsts = $('#sec-hsts-profile').value;
        const r = await fetch('/api/wiz/admin/sec/headers', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ csp_profile: csp, csp_custom: null, hsts_profile: hsts }),
        });
        const d = await r.json();
        if (!r.ok) { _secMsg(d.detail || 'save failed', false); return; }
        _secMsg(d.note || 'saved', true);
    });

    $('#btn-sec-panic')?.addEventListener('click', async () => {
        const s = prompt('Напиши ровно «WIPE AND STOP» чтобы подтвердить panic:');
        if (s !== 'WIPE AND STOP') return;
        const r = await fetch('/api/wiz/admin/sec/panic', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ confirm: s }),
        });
        const d = await r.json();
        if (!r.ok) { _secMsg(d.detail || 'panic failed', false); return; }
        _secMsg(`Удалено: ${(d.removed||[]).length} элемент(а). Wizard вернётся в setup.`, true);
        setTimeout(() => location.reload(), 2000);
    });

    async function loadOpsJobs() {
        const tbody = $('#ops-jobs-tbody');
        if (!tbody) return;
        clear(tbody);
        try {
            const r = await fetch('/api/wiz/admin/ops/jobs');
            const d = await r.json();
            d.jobs.forEach(j => {
                const tr = document.createElement('tr');
                tr.appendChild(td(j.name));
                // Interval select
                const iTd = document.createElement('td');
                const sel = document.createElement('select');
                sel.className = 'form-input';
                sel.style.padding = '2px 6px';
                sel.style.fontSize = '12px';
                d.presets.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p; opt.textContent = p;
                    if (p === j.interval) opt.selected = true;
                    sel.appendChild(opt);
                });
                sel.addEventListener('change', async () => {
                    await fetch('/api/wiz/admin/ops/jobs/' + encodeURIComponent(j.name), {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ interval: sel.value }),
                    });
                    toast(j.name + ' → ' + sel.value);
                });
                iTd.appendChild(sel);
                tr.appendChild(iTd);
                tr.appendChild(td(j.last_run ? new Date(j.last_run * 1000).toLocaleString() : '—'));
                const okTd = td(j.last_run ? (j.last_ok ? 'ok' : 'error') : 'never');
                if (j.last_run) okTd.style.color = j.last_ok ? '#22c55e' : '#ef4444';
                tr.appendChild(okTd);
                tr.appendChild(td(j.last_msg || ''));
                const actTd = document.createElement('td');
                const btn = document.createElement('button');
                btn.className = 'btn-small';
                btn.textContent = 'Run now';
                btn.addEventListener('click', async () => {
                    btn.disabled = true; btn.textContent = '…';
                    try {
                        const rr = await fetch('/api/wiz/admin/ops/jobs/' + encodeURIComponent(j.name) + '/run', {method:'POST'});
                        const dd = await rr.json();
                        toast(j.name + ': ' + (dd.result?.message || 'done'));
                        loadOpsJobs();
                    } catch (e) { toast(String(e)); }
                    btn.disabled = false; btn.textContent = 'Run now';
                });
                actTd.appendChild(btn);
                tr.appendChild(actTd);
                tbody.appendChild(tr);
            });
        } catch (e) {
            console.warn('ops jobs', e);
        }
    }

    async function loadOpsUptime() {
        try {
            const r = await fetch('/api/wiz/admin/ops/uptime');
            const d = await r.json();
            const pctEl = $('#ops-uptime-pct');
            if (pctEl) {
                pctEl.textContent = d.uptime_pct + '% (' + d.up_samples + '/' + d.total_samples + ' probes)';
                pctEl.style.color = d.uptime_pct >= 99 ? '#22c55e' : (d.uptime_pct >= 95 ? '#eab308' : '#ef4444');
            }
            const img = $('#ops-uptime-badge');
            if (img) img.src = '/api/wiz/admin/ops/uptime/badge.svg?t=' + Date.now();
            const url = $('#ops-uptime-url');
            if (url) url.textContent = window.location.origin + '/api/wiz/admin/ops/uptime/badge.svg';
        } catch (e) {
            console.warn('uptime', e);
        }
    }

    async function loadOpsVersion() {
        try {
            const r = await fetch('/api/wiz/admin/ops/version');
            const d = await r.json();
            const v = $('#ops-version'); if (v) v.textContent = d.version || '—';
            const t = $('#ops-pin-toggle'); if (t) t.checked = !!d.pinned;
        } catch (e) {}
    }

    $('#ops-pin-toggle')?.addEventListener('change', async () => {
        const t = $('#ops-pin-toggle');
        try {
            await fetch('/api/wiz/admin/ops/version/pin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pinned: !!t.checked }),
            });
            toast(t.checked ? 'Version pinned' : 'Pin released');
        } catch (e) { toast(String(e)); }
    });

    async function loadAuditEntries() {
        const onlyAlert = $('#obs-audit-only-alert')?.checked || false;
        const tbody = $('#obs-audit-tbody');
        const summary = $('#obs-audit-summary');
        if (!tbody) return;
        clear(tbody);
        try {
            const r = await fetch('/api/wiz/admin/audit?limit=100&only_alert=' + (onlyAlert ? '1' : '0'));
            const d = await r.json();
            summary.textContent = `${d.total} entries · ${d.alert_total} alerts · ${d.known_ips.length} known IPs`;
            if (!d.entries.length) {
                const row = document.createElement('tr');
                const tdd = document.createElement('td'); tdd.colSpan = 7; tdd.className = 'empty';
                tdd.textContent = onlyAlert ? 'no alerts' : '—';
                row.appendChild(tdd); tbody.appendChild(row);
                return;
            }
            d.entries.forEach(e => {
                const tr = document.createElement('tr');
                const when = new Date((e.ts || 0) * 1000).toLocaleString();
                tr.appendChild(td(when));
                tr.appendChild(td(e.method));
                tr.appendChild(td(e.path));
                const ipTd = document.createElement('td');
                ipTd.textContent = e.client_ip || '—';
                if (e.alert) {
                    const btn = document.createElement('button');
                    btn.className = 'btn-small';
                    btn.style.marginLeft = '6px';
                    btn.style.fontSize = '10px';
                    btn.textContent = 'trust';
                    btn.addEventListener('click', async () => {
                        await fetch('/api/wiz/admin/audit/trust_ip', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ ip: e.client_ip }),
                        });
                        loadAuditEntries();
                    });
                    ipTd.appendChild(btn);
                }
                tr.appendChild(ipTd);
                tr.appendChild(td(String(e.status || '—')));
                tr.appendChild(td(String(e.duration_ms || 0)));
                const alertTd = document.createElement('td');
                if (e.alert) {
                    const span = document.createElement('span');
                    span.style.color = '#f59e0b';
                    span.textContent = '⚠ ' + (e.alert_reason || '');
                    alertTd.appendChild(span);
                }
                tr.appendChild(alertTd);
                tbody.appendChild(tr);
            });
        } catch (e) {
            summary.textContent = 'error: ' + e;
        }
    }

    $('#obs-audit-refresh')?.addEventListener('click', loadAuditEntries);
    $('#obs-audit-only-alert')?.addEventListener('change', loadAuditEntries);
    $('#obs-audit-clear')?.addEventListener('click', async () => {
        if (!confirm('Очистить весь audit log? Это необратимо.')) return;
        await fetch('/api/wiz/admin/audit/clear', { method: 'POST' });
        loadAuditEntries();
    });

    async function loadProfiler() {
        const tbody = $('#obs-prof-tbody');
        if (!tbody) return;
        clear(tbody);
        try {
            const r = await fetch('/api/wiz/admin/profiler?top=20');
            const d = await r.json();
            if (!d.endpoints.length) {
                const row = document.createElement('tr');
                const tdd = document.createElement('td'); tdd.colSpan = 6; tdd.className = 'empty';
                tdd.textContent = 'нет данных — походи по UI, чтобы засеять профайлер';
                row.appendChild(tdd); tbody.appendChild(row);
                return;
            }
            d.endpoints.forEach(e => {
                const tr = document.createElement('tr');
                tr.appendChild(td(e.method));
                tr.appendChild(td(e.path));
                tr.appendChild(td(String(e.count)));
                tr.appendChild(td(e.p50_ms + ' ms'));
                tr.appendChild(td(e.p95_ms + ' ms'));
                const p99Td = td(e.p99_ms + ' ms');
                if (e.p99_ms > 1000) p99Td.style.color = '#f59e0b';
                if (e.p99_ms > 3000) p99Td.style.color = '#ef4444';
                tr.appendChild(p99Td);
                tbody.appendChild(tr);
            });
        } catch (e) {
            console.warn('profiler fetch', e);
        }
    }

    $('#obs-prof-refresh')?.addEventListener('click', loadProfiler);
    $('#obs-prof-reset')?.addEventListener('click', async () => {
        await fetch('/api/wiz/admin/profiler/reset', { method: 'POST' });
        loadProfiler();
    });

    async function loadLogFiles() {
        const summary = $('#obs-logs-summary');
        const files = $('#obs-logs-files');
        if (!summary || !files) return;
        files.textContent = '';
        try {
            const r = await fetch('/api/wiz/admin/logs/files');
            const d = await r.json();
            const totalBytes = d.files.reduce((s, f) => s + f.byte_size, 0);
            summary.textContent = `${d.files.length} файлов, суммарно ${_fmtBytes(totalBytes)}. Rotation threshold ${_fmtBytes(d.threshold)}, max kept ${d.max_kept}.`;
            d.files.forEach(f => {
                const div = document.createElement('div');
                const gz = f.compressed ? ' (gz)' : '';
                div.textContent = `${f.name}${gz} · ${_fmtBytes(f.byte_size)} · ${new Date(f.modified * 1000).toLocaleString()}`;
                files.appendChild(div);
            });
        } catch (e) {
            summary.textContent = 'error: ' + e;
        }
    }

    $('#obs-logs-rotate')?.addEventListener('click', async () => {
        const r = await fetch('/api/wiz/admin/logs/rotate', { method: 'POST' });
        const d = await r.json();
        toast(d.rotated.length ? 'Rotated: ' + d.rotated.join(', ') : 'Nothing to rotate');
        loadLogFiles();
    });

    $('#obs-logs-search')?.addEventListener('click', async () => {
        const q = $('#obs-logs-query')?.value?.trim() || '';
        if (!q) { toast('введи запрос'); return; }
        const pre = $('#obs-logs-hits');
        pre.style.display = '';
        pre.textContent = 'searching…';
        try {
            const r = await fetch('/api/wiz/admin/logs/search?q=' + encodeURIComponent(q));
            const d = await r.json();
            if (!d.hits.length) {
                pre.textContent = 'no hits';
                return;
            }
            pre.textContent = d.hits.map(h => `[${h.file}:${h.line}] ${h.text}`).join('\n')
                + (d.truncated ? '\n\n… (truncated, refine query)' : '');
        } catch (e) {
            pre.textContent = 'error: ' + e;
        }
    });

    $('#obs-logs-query')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') $('#obs-logs-search').click();
    });

    // ── AI (Ollama one-click setup) ───────────────────────────────────
    function _aiMsg(text, ok) {
        const el = $('#ai-msg'); if (!el) return;
        el.textContent = text || '';
        el.className = 'alert ' + (text ? (ok ? 'alert-ok show' : 'alert-err show') : '');
    }

    function _aiLayoutByState(enabled) {
        const master     = $('#ai-master');
        const slotStart  = $('#ai-master-slot-start');
        const slotEnd    = $('#ai-master-slot-end');
        const stack      = $('#ai-stack');
        if (!master || !slotStart || !slotEnd || !stack) return;

        if (enabled) {
            // AI ON → stack of detail cards visible, master toggle drops
            // to the bottom as a "disable" control.
            stack.style.display = '';
            slotEnd.appendChild(master);
            const sub = $('#ai-master-subtitle');
            const lbl = $('#ai-master-label strong');
            if (lbl) lbl.textContent = 'AI включён';
            if (sub) sub.textContent = 'Выключить — контроллер снизит вес этой ноды на 15%';
        } else {
            // AI OFF → ONLY the master toggle is shown, front-and-center.
            stack.style.display = 'none';
            slotStart.appendChild(master);
            const sub = $('#ai-master-subtitle');
            const lbl = $('#ai-master-label strong');
            if (lbl) lbl.textContent = 'Включить локальный AI';
            if (sub) sub.textContent = 'Поставит Ollama одним кликом и разблокирует установку модели. Без AI вес ноды снижен на 15%.';
        }
    }

    async function loadAiStatus() {
        try {
            const r = await fetch('/api/wiz/admin/ai/status');
            const d = await r.json();

            // Layout first — if AI is off, the sub-cards don't even
            // render, so querySelectors below can return null. That's
            // fine; we only touch them when the stack is visible.
            _aiLayoutByState(!!d.ai_enabled);

            const toggle = $('#ai-toggle');
            if (toggle) toggle.checked = !!d.ai_enabled;

            if (!d.ai_enabled) return;   // rest of the UI is hidden

            $('#ai-installed').textContent = d.installed ? '✓ ' + (d.ollama_path || '') : '— не установлен';
            $('#ai-running').textContent   = d.running ? '✓ запущен' : '— остановлен';
            $('#ai-configured-model').textContent = d.configured_model || d.default_model || '—';
            $('#ai-models').textContent = (d.models || []).length
                ? d.models.join(', ')
                : '— моделей нет';
            const modelInput = $('#ai-model-input');
            if (modelInput && !modelInput.value) modelInput.value = d.configured_model || d.default_model;

            // Detect if the currently-configured model is ALREADY in the
            // local ollama registry. Model names can have an implicit
            // :latest tag, so compare with and without it.
            const pullBtn    = $('#btn-ai-pull');
            const wantModel  = (modelInput?.value || d.configured_model || d.default_model || '').trim();
            const have = (d.models || []).map(m => m.toLowerCase());
            const wantLc = wantModel.toLowerCase();
            const modelInstalled = have.includes(wantLc)
                                || have.includes(wantLc + ':latest')
                                || (wantLc.endsWith(':latest') && have.includes(wantLc.slice(0,-7)));

            if (pullBtn) {
                if (!d.installed) {
                    pullBtn.disabled = true;
                    pullBtn.textContent = 'Install Ollama first';
                } else if (modelInstalled) {
                    pullBtn.disabled = true;
                    pullBtn.textContent = '✓ Already installed';
                } else {
                    pullBtn.disabled = false;
                    pullBtn.textContent = 'Pull model';
                }
            }

            $('#btn-ai-start').disabled     = !d.installed || d.running;
            $('#btn-ai-stop').disabled      = !d.running;
            $('#btn-ai-install').disabled   = d.installed;
            $('#btn-ai-uninstall').disabled = !d.installed;
            // Reflect install state textually for clarity
            const installBtn = $('#btn-ai-install');
            if (installBtn) installBtn.textContent = d.installed ? '✓ Installed' : 'Install';
            const startBtn = $('#btn-ai-start');
            if (startBtn) startBtn.textContent = d.running ? '✓ Running' : 'Start';
        } catch (e) {
            _aiMsg('Ошибка статуса: ' + e, false);
        }
    }

    $('#btn-ai-refresh')?.addEventListener('click', loadAiStatus);

    // Delegate on <body> because the toggle element gets re-parented
    // between two slots by _aiLayoutByState — direct binding would
    // desync after first relayout.
    document.body.addEventListener('change', async (ev) => {
        if (ev.target && ev.target.id === 'ai-toggle') {
            const t = ev.target;
            try {
                const r = await fetch('/api/wiz/admin/ai/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: !!t.checked }),
                });
                const d = await r.json();
                if (!r.ok) { _aiMsg(d.detail || 'toggle failed', false); return; }
                _aiMsg(t.checked
                    ? 'AI включён — перезапусти ноду; контроллер увидит флаг на следующем heartbeat'
                    : 'AI выключен — вес ноды в /v1/nodes/random снижен на 15%', true);
                await loadAiStatus();  // relayout + show/hide details
            } catch (e) { _aiMsg(String(e), false); }
        }
    });

    $('#btn-ai-install')?.addEventListener('click', async () => {
        const btn = $('#btn-ai-install');
        btn.disabled = true;
        const prev = btn.textContent;
        btn.textContent = 'Устанавливается… (до 10 мин)';
        _aiMsg('brew install ollama — загрузка пакета', true);
        try {
            const r = await fetch('/api/wiz/admin/ai/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ use_homebrew: true }),
            });
            const d = await r.json();
            if (!r.ok) { _aiMsg(d.detail || 'install failed', false); }
            else if (d.manual) {
                _aiMsg('На Linux запусти в терминале: ' + d.command, true);
            } else {
                _aiMsg('Установлено ✓ (' + (d.installed_via || 'ok') + ')', true);
                await loadAiStatus();
            }
        } catch (e) { _aiMsg(String(e), false); }
        btn.disabled = false;
        btn.textContent = prev;
    });

    $('#btn-ai-pull')?.addEventListener('click', async () => {
        const model = ($('#ai-model-input')?.value || '').trim();
        if (!model) { _aiMsg('введи имя модели', false); return; }
        const btn = $('#btn-ai-pull');
        btn.disabled = true;
        const prev = btn.textContent;
        btn.textContent = 'Скачиваю… (GB, до часа)';
        _aiMsg('Pulling ' + model + ' — проверяй терминал ноды для прогресса', true);
        try {
            const r = await fetch('/api/wiz/admin/ai/pull', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model }),
            });
            const d = await r.json();
            if (!r.ok) { _aiMsg(d.detail || 'pull failed', false); }
            else { _aiMsg('Модель ' + d.model + ' загружена', true); await loadAiStatus(); }
        } catch (e) { _aiMsg(String(e), false); }
        btn.disabled = false;
        btn.textContent = prev;
    });

    $('#btn-ai-start')?.addEventListener('click', async () => {
        _aiMsg('Запускаю ollama serve…', true);
        try {
            const r = await fetch('/api/wiz/admin/ai/start', { method: 'POST' });
            const d = await r.json();
            _aiMsg(d.ok ? 'Daemon запущен' : (d.message || 'start failed'), d.ok);
            await loadAiStatus();
        } catch (e) { _aiMsg(String(e), false); }
    });

    $('#btn-ai-stop')?.addEventListener('click', async () => {
        _aiMsg('Останавливаю daemon…', true);
        try {
            await fetch('/api/wiz/admin/ai/stop', { method: 'POST' });
            _aiMsg('Daemon остановлен', true);
            await loadAiStatus();
        } catch (e) { _aiMsg(String(e), false); }
    });

    $('#btn-ai-uninstall')?.addEventListener('click', async () => {
        if (!confirm('Удалить ollama? Скачанные модели останутся в ~/.ollama — удали вручную чтобы освободить диск.')) return;
        _aiMsg('Удаляю ollama…', true);
        try {
            const r = await fetch('/api/wiz/admin/ai/uninstall', { method: 'POST' });
            const d = await r.json();
            if (!r.ok) { _aiMsg(d.detail || 'uninstall failed', false); return; }
            _aiMsg('Удалено ✓', true);
            await loadAiStatus();
        } catch (e) { _aiMsg(String(e), false); }
    });

    // ── Settings panel (full .env editor) ─────────────────────────────
    let _settingsState = null;

    function _settingsMsg(text, ok) {
        const el = $('#settings-msg'); if (!el) return;
        el.textContent = text || '';
        el.className = 'alert ' + (text ? (ok ? 'alert-ok show' : 'alert-err show') : '');
    }

    async function loadSettings() {
        try {
            const r = await fetch('/api/wiz/admin/settings');
            const d = await r.json();
            _settingsState = d;
            _renderSettings(d);
        } catch (e) {
            _settingsMsg('Не удалось загрузить настройки: ' + e, false);
        }
    }

    function _renderSettings(d) {
        const host = $('#settings-groups');
        if (!host) return;
        clear(host);
        const filter = ($('#settings-filter')?.value || '').trim().toLowerCase();
        const byGroup = new Map();
        d.fields.forEach(f => {
            if (filter && !(
                (f.key || '').toLowerCase().includes(filter) ||
                (f.label || '').toLowerCase().includes(filter) ||
                (f.desc || '').toLowerCase().includes(filter)
            )) return;
            if (!byGroup.has(f.group)) byGroup.set(f.group, []);
            byGroup.get(f.group).push(f);
        });

        (d.groups_order || []).forEach(g => {
            const fields = byGroup.get(g); if (!fields || !fields.length) return;
            const card = document.createElement('div');
            card.className = 'card';
            const h = document.createElement('h3'); h.textContent = g;
            card.appendChild(h);
            fields.forEach(f => card.appendChild(_settingsField(f)));
            host.appendChild(card);
        });
    }

    function _settingsField(f) {
        const row = document.createElement('div');
        row.className = 'card-row';
        row.style.alignItems = 'flex-start';
        row.style.padding = '8px 0';

        const left = document.createElement('div');
        left.style.flex = '1';
        const label = document.createElement('div');
        label.style.fontSize = '13px';
        label.style.fontWeight = '600';
        label.textContent = f.label || f.key;
        const code = document.createElement('code');
        code.style.cssText = 'font-size:10px; color:var(--text2); display:block; margin-top:2px;';
        code.textContent = f.key + (f.requires_restart ? ' · рестарт ноды' : '');
        left.appendChild(label); left.appendChild(code);
        if (f.desc) {
            const desc = document.createElement('div');
            desc.style.cssText = 'font-size:11px; color:var(--text2); margin-top:4px; line-height:1.5;';
            desc.textContent = f.desc;
            left.appendChild(desc);
        }
        row.appendChild(left);

        const right = document.createElement('div');
        right.style.minWidth = '260px';
        right.style.marginLeft = '16px';

        let input;
        if (f.type === 'bool') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = ['1','true','yes','on'].includes(String(f.value || '').toLowerCase());
            input.addEventListener('change', () => _saveField(f.key, input.checked));
        } else if (f.type === 'select') {
            input = document.createElement('select');
            input.className = 'form-input';
            input.style.minWidth = '200px';
            (f.options || []).forEach(opt => {
                const o = document.createElement('option');
                o.value = opt; o.textContent = opt;
                if (String(f.value) === opt) o.selected = true;
                input.appendChild(o);
            });
            input.addEventListener('change', () => _saveField(f.key, input.value));
        } else if (f.type === 'textarea') {
            input = document.createElement('textarea');
            input.className = 'form-input';
            input.rows = 3;
            input.style.width = '260px';
            input.value = f.value || '';
            input.addEventListener('blur', () => _saveField(f.key, input.value));
        } else if (f.type === 'password') {
            const wrap = document.createElement('div');
            wrap.style.display = 'flex';
            wrap.style.gap = '6px';
            input = document.createElement('input');
            input.type = 'password';
            input.className = 'form-input';
            input.value = f.is_set ? '••••••••••' : '';
            input.placeholder = f.is_set ? 'saved (reveal to edit)' : '';
            input.addEventListener('blur', () => {
                if (input.value && input.value !== '••••••••••') _saveField(f.key, input.value);
            });
            const reveal = document.createElement('button');
            reveal.className = 'btn-small';
            reveal.textContent = 'reveal';
            reveal.addEventListener('click', async () => {
                if (!confirm('Показать секретное значение ' + f.key + '?')) return;
                try {
                    const r = await fetch('/api/wiz/admin/settings/reveal', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ key: f.key, confirm: 'REVEAL' }),
                    });
                    const d = await r.json();
                    if (r.ok) { input.type = 'text'; input.value = d.value || ''; }
                    else _settingsMsg(d.detail || 'reveal failed', false);
                } catch (e) { _settingsMsg(String(e), false); }
            });
            wrap.appendChild(input); wrap.appendChild(reveal);
            right.appendChild(wrap);
            row.appendChild(right);
            return row;
        } else {
            // str or int or advanced
            input = document.createElement('input');
            input.type = (f.type === 'int') ? 'number' : 'text';
            input.className = 'form-input';
            input.style.width = '260px';
            input.value = f.value || '';
            input.addEventListener('blur', () => _saveField(f.key, input.value));
            input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });
        }
        right.appendChild(input);
        row.appendChild(right);
        return row;
    }

    async function _saveField(key, value) {
        try {
            const r = await fetch('/api/wiz/admin/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ changes: { [key]: value } }),
            });
            const d = await r.json();
            if (!r.ok) { _settingsMsg(key + ': ' + (d.detail || 'fail'), false); return; }
            const msg = `${key} → сохранено` + (d.requires_restart ? ' · требуется рестарт ноды' : '');
            _settingsMsg(msg, true);
        } catch (e) { _settingsMsg(String(e), false); }
    }

    $('#btn-settings-refresh')?.addEventListener('click', loadSettings);
    $('#settings-filter')?.addEventListener('input', () => {
        if (_settingsState) _renderSettings(_settingsState);
    });

    // ── Restore-on-new-device banner ──────────────────────────────────
    // Shows when:
    //   * there's a backup on the controller,
    //   * local DB looks "fresh" (very small — < 256 KiB) or doesn't exist,
    //   * the user hasn't already dismissed it for this pubkey.
    // A fresh sqlite-from-create_all is typically 150–200 KB, so the
    // threshold separates a just-restored identity from a real in-use node.
    const _FRESH_DB_BYTES = 256 * 1024;

    function _restoreBannerDismissKey(pub) {
        return `vx_restore_banner_dismissed:${pub || 'unknown'}`;
    }

    async function _maybeShowRestoreBanner() {
        const banner = $('#restore-banner');
        if (!banner) return;
        let pub = '';
        try {
            const idRes = await fetch('/api/wiz/admin/identity').then(r => r.json());
            pub = (idRes && idRes.pubkey) || '';
        } catch (_) { /* ignore */ }

        try {
            const dismissed = localStorage.getItem(_restoreBannerDismissKey(pub)) === '1';
            if (dismissed) { banner.style.display = 'none'; return; }
        } catch (_) { /* storage blocked — keep going */ }

        let d = null;
        try {
            const r = await fetch('/api/wiz/admin/backup/status');
            d = await r.json();
        } catch (_) { return; }

        if (!d || !d.remote_exists) { banner.style.display = 'none'; return; }
        if (!d.supported)            { banner.style.display = 'none'; return; }

        const localSize = Number(d.database_byte_size || 0);
        const looksFresh = !d.database_exists || localSize < _FRESH_DB_BYTES;
        if (!looksFresh) { banner.style.display = 'none'; return; }

        const desc = $('#restore-banner-desc');
        if (desc) {
            const when = d.remote_updated_at
                ? new Date(d.remote_updated_at * 1000).toLocaleString()
                : '—';
            const size = _fmtBytes(d.remote_byte_size || 0);
            desc.textContent = `${size} · обновлён ${when}. Если это то же устройство — пропусти.`;
        }
        banner.style.display = '';
    }

    $('#restore-banner-skip')?.addEventListener('click', async () => {
        try {
            const idRes = await fetch('/api/wiz/admin/identity').then(r => r.json());
            const pub = (idRes && idRes.pubkey) || '';
            localStorage.setItem(_restoreBannerDismissKey(pub), '1');
        } catch (_) { /* storage blocked — just hide */ }
        $('#restore-banner').style.display = 'none';
    });

    $('#restore-banner-do')?.addEventListener('click', async () => {
        // Gate: node must be stopped before a restore can clobber vortex.db.
        // Best-effort check via /node/status; if alive, tell the user.
        let alive = false;
        try {
            const s = await fetch('/api/wiz/admin/node/status').then(r => r.json());
            alive = !!(s.process_alive || s.http_reachable);
        } catch (_) {}
        if (alive) {
            toast('Останови ноду в сайдбаре, потом жми «Восстановить сейчас»', 4000);
            return;
        }
        if (!confirm('Восстановить базу с контроллера? Текущий (пустой) vortex.db будет заменён.')) return;

        const btn = $('#restore-banner-do');
        btn.disabled = true;
        const prev = btn.textContent;
        btn.textContent = 'Восстанавливаю…';
        try {
            const r = await fetch('/api/wiz/admin/backup/restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: true }),
            });
            const txt = await r.text();
            let d = null; try { d = JSON.parse(txt); } catch {}
            if (!r.ok) {
                toast('Ошибка: ' + ((d && d.detail) || txt.slice(0, 160)), 5000);
            } else {
                toast(`Готово: восстановлено ${_fmtBytes(d.plaintext_byte_size)}. Жми «Start node».`, 5000);
                // Dismiss banner — nothing else to restore.
                try {
                    const idRes = await fetch('/api/wiz/admin/identity').then(r => r.json());
                    localStorage.setItem(_restoreBannerDismissKey((idRes && idRes.pubkey) || ''), '1');
                } catch (_) {}
                $('#restore-banner').style.display = 'none';
            }
        } catch (e) {
            toast(String(e), 4000);
        }
        btn.disabled = false;
        btn.textContent = prev;
    });

    // ── Initial + polling ─────────────────────────────────────────────
    async function refreshAll() {
        try {
            await Promise.all([
                loadIdentity(),
                loadController(),
                loadPeers(),
                loadTraffic(),
                loadCerts(),
                loadNodeStatus(),
            ]);
        } catch (e) {
            console.warn('refresh failed:', e);
        }
    }

    (async () => {
        await loadRepoIntegrity();
        await refreshAll();
        // Fire once, after identity/status have been populated — the
        // banner only shows when local DB is empty and a remote backup
        // exists, so it's cheap on steady-state nodes.
        _maybeShowRestoreBanner().catch(() => {});
        setInterval(refreshAll, POLL_INTERVAL_MS);
    })();
})();
