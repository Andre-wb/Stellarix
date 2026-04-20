/* Setup wizard — 4-step flow:
 *   1  Identity + network mode
 *   2  Public exposure pick (tunnel / manual / skip)   [skipped for Local]
 *   3  Detail of chosen exposure                        [skipped for Local]
 *   4  Review & Create
 *
 * Clicking a choice card in step 2 immediately advances to step 3 with
 * the matching detail view. Each detail view has its own nav bar.
 */
(() => {
    'use strict';

    const $  = s => document.querySelector(s);
    const $$ = s => [...document.querySelectorAll(s)];

    const state = {
        step: 1,
        mode: 'local',
        exposure: null,
        tunnelUrl: null,
        manualUrl: '',
        sns: null,
        mnemonic: null,      // 24-word phrase (kept in memory only)
        nodePubkey: null,    // Ed25519 pubkey derived from mnemonic
        walletPubkey: null,  // Solana wallet derived from mnemonic
    };

    function i18n(k, f) {
        const v = window.VortexI18n ? window.VortexI18n.t(k) : null;
        return (typeof v === 'string' && v !== k) ? v : f;
    }

    function showMsg(text, variant) {
        const msg = $('#msg');
        if (!msg) return;
        msg.textContent = text;
        msg.className = 'alert show ' + (variant === 'ok' ? 'alert-ok' : 'alert-err');
    }

    // ── Step dots — render dynamically by current flow ────────────────
    //
    // Step numbering (matches data-step attributes on DOM elements):
    //   1 — identity (create / restore)  — the ``#identity-block`` div
    //   2 — device + network mode        — data-step="2"
    //   3 — exposure choice              — data-step="3"
    //   4 — exposure detail              — data-step="4"
    //   5 — review + create              — data-step="5"
    //
    // Local mode skips 3 and 4, so its flow is: 1 → 2 → 5.
    function flowSteps() {
        return state.mode === 'local'
            ? [1, 2, 5]
            : [1, 2, 3, 4, 5];
    }
    function renderDots() {
        const host = $('#step-dots');
        while (host.firstChild) host.removeChild(host.firstChild);
        const steps = flowSteps();
        steps.forEach((s, i) => {
            if (i > 0) {
                const line = document.createElement('div');
                line.className = 'line';
                host.appendChild(line);
            }
            const d = document.createElement('div');
            d.className = 'dot';
            d.dataset.step = s;
            const n = document.createElement('span');
            n.textContent = steps.indexOf(s) + 1;
            d.appendChild(n);
            if (s === state.step) d.classList.add('active');
            else if (steps.indexOf(s) < steps.indexOf(state.step)) d.classList.add('done');
            host.appendChild(d);
        });
    }

    function showStep(n) {
        state.step = n;
        // step 1 is identity — its own block, not a .step-view
        idBlock.style.display = (n === 1) ? '' : 'none';
        $$('.step-view').forEach(v => v.classList.toggle('active', +v.dataset.step === n));
        renderDots();
        if (n === 4) applyDetailView();   // detail page
        if (n === 5) renderSummary();     // review page
    }

    // ── Identity block (shown before the numbered wizard) ─────────────
    const idBlock = $('#identity-block');
    const stepDots = $('#step-dots');

    function showIdentityView(name) {
        state.step = 1;
        idBlock.style.display = '';
        $$('.step-view').forEach(v => v.classList.remove('active'));
        $$('.identity-view').forEach(v => {
            v.style.display = (v.dataset.view === name) ? '' : 'none';
        });
        renderDots();
    }

    function beginWizard() {
        // After identity (step 1) is complete, move to step 2 (device + mode).
        showStep(2);
    }

    $$('[data-id-action="create"]').forEach(b => b.addEventListener('click', async () => {
        showIdentityView('create');
        const grid = $('#seed-grid');
        grid.textContent = i18n('setup.generatingSeed', 'Generating…');
        try {
            const r = await fetch('/api/wiz/setup/generate-seed');
            const d = await r.json();
            state.mnemonic = d.mnemonic;
            state.nodePubkey = d.node_pubkey;
            state.walletPubkey = d.wallet_pubkey;
            renderSeedGrid(d.words);
            $('#derived-node').textContent = d.node_pubkey;
            $('#derived-wallet').textContent = d.wallet_pubkey;
            $('#seed-derived').style.display = '';
        } catch (e) {
            grid.textContent = '⚠ ' + String(e);
        }
    }));

    $$('[data-id-action="restore"]').forEach(b => b.addEventListener('click', () => {
        showIdentityView('restore');
        $('#restore-words').focus();
    }));

    $('#btn-id-back-create').addEventListener('click', () => showIdentityView('choice'));
    $('#btn-id-back-restore').addEventListener('click', () => showIdentityView('choice'));

    function renderSeedGrid(words) {
        const grid = $('#seed-grid');
        while (grid.firstChild) grid.removeChild(grid.firstChild);
        words.forEach((w, i) => {
            const cell = document.createElement('div');
            cell.className = 'seed-cell';
            const idx = document.createElement('span');
            idx.className = 'seed-idx';
            idx.textContent = String(i + 1);
            const word = document.createElement('span');
            word.className = 'seed-word';
            word.textContent = w;
            cell.appendChild(idx);
            cell.appendChild(word);
            grid.appendChild(cell);
        });
    }

    $('#seed-saved').addEventListener('change', (e) => {
        $('#btn-id-continue-create').disabled = !e.target.checked;
    });

    $('#btn-copy-seed').addEventListener('click', async () => {
        if (!state.mnemonic) return;
        try { await navigator.clipboard.writeText(state.mnemonic); } catch {}
        const b = $('#btn-copy-seed');
        const orig = b.textContent;
        b.textContent = i18n('setup.copied', 'Copied ✓');
        setTimeout(() => { b.textContent = orig; }, 1200);
    });

    $('#btn-download-seed').addEventListener('click', () => {
        if (!state.mnemonic) return;
        const blob = new Blob([state.mnemonic + '\n'], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'vortex-seed.txt';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });

    $('#btn-id-continue-create').addEventListener('click', beginWizard);

    $('#btn-id-continue-restore').addEventListener('click', async () => {
        const words = ($('#restore-words').value || '').trim();
        const msg = $('#restore-msg');
        msg.className = 'alert';
        msg.textContent = '';
        try {
            const r = await fetch('/api/wiz/setup/validate-seed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mnemonic: words }),
            });
            const d = await r.json();
            if (!d.ok) {
                msg.className = 'alert show alert-err';
                msg.textContent = '⚠ ' + (d.error || 'invalid phrase');
                return;
            }
            state.mnemonic = words;
            state.nodePubkey = d.node_pubkey;
            state.walletPubkey = d.wallet_pubkey;
            // Briefly reveal derived keys so the user sees which wallet
            // they just restored, then enter the wizard.
            $('#restore-node').textContent = d.node_pubkey;
            $('#restore-wallet').textContent = d.wallet_pubkey;
            $('#restore-derived').style.display = '';
            setTimeout(beginWizard, 600);
        } catch (e) {
            msg.className = 'alert show alert-err';
            msg.textContent = '⚠ ' + String(e);
        }
    });

    function applyDetailView() {
        $$('.step-detail').forEach(el => {
            el.style.display = (el.dataset.detail === state.exposure) ? '' : 'none';
        });
        // For tunnel detail, keep port label current
        const p = $('#tunnel-port-label');
        if (p) p.textContent = String(parseInt($('#port').value, 10) || 9000);
    }

    // ── Step 1 — mode cards + custom fields ───────────────────────────
    const modeCards = $$('#mode-cards .mode-card');
    const customFields = $('#custom-fields');
    const hiddenMode = $('#network_mode');

    function syncCustomFields() {
        customFields.style.display = (state.mode === 'custom') ? '' : 'none';
    }

    modeCards.forEach(c => c.addEventListener('click', () => {
        modeCards.forEach(x => x.classList.toggle('selected', x === c));
        state.mode = c.dataset.mode;
        hiddenMode.value = state.mode;
        syncCustomFields();
    }));
    syncCustomFields();

    fetch('/api/wiz/setup/system').then(r => r.json()).then(d => {
        const el = $('#device_name');
        if (el && !el.value && d.hostname) el.value = d.hostname;
    }).catch(() => {});

    $('#btn-next-1').addEventListener('click', () => {
        // This is the "Continue" button on the device + mode screen
        // (step 2 in the new numbering; the button id stays btn-next-1
        // for backwards compatibility with existing i18n/CSS selectors).
        if (!$('#device_name').value.trim()) {
            $('#device_name').focus();
            return;
        }
        if (state.mode === 'custom' && !$('#controller_url').value.trim()) {
            $('#controller_url').focus();
            return;
        }
        // Local → jump straight to Review (step 5)
        if (state.mode === 'local') {
            state.exposure = 'skip';
            showStep(5);
        } else {
            showStep(3);
        }
    });

    // ── Step 3 — choice cards (click = advance to step 4) ─────────────
    $$('#tunnel-cards .choice-card').forEach(c => c.addEventListener('click', () => {
        state.exposure = c.dataset.choice;
        $$('#tunnel-cards .choice-card').forEach(x => x.classList.toggle('selected', x === c));
        showStep(4);
        if (state.exposure === 'tunnel') refreshTunnelStatus();
    }));
    $('#btn-back-2').addEventListener('click', () => showStep(2));

    // ── Step 3 — detail views ─────────────────────────────────────────
    function setCtaMode(mode) {
        const startBtn = $('#btn-start-tunnel');
        const label = $('#btn-start-tunnel-label');
        if (mode === 'regenerate') {
            startBtn.classList.add('secondary');
            label.textContent = i18n('setup.regenerate', 'Regenerate');
        } else {
            startBtn.classList.remove('secondary');
            label.textContent = i18n('setup.generateTunnel', 'Generate tunnel');
        }
    }

    async function refreshTunnelStatus() {
        try {
            const r = await fetch('/api/wiz/setup/tunnel-status');
            const d = await r.json();
            const startBtn = $('#btn-start-tunnel');
            const stopBtn  = $('#btn-stop-tunnel');
            const urlBox   = $('#tunnel-url-box');
            const tu       = $('#tunnel-url');
            const tstate   = $('#tunnel-state');
            const tlabel   = $('#tunnel-state-label');

            state.tunnelUrl = d.url || null;

            if (!d.installed) {
                tstate.dataset.state = 'err';
                tlabel.textContent = '⚠ cloudflared is not installed (brew install cloudflared)';
                urlBox.style.display = 'none';
                startBtn.disabled = true;
                stopBtn.style.display = 'none';
                setCtaMode('primary');
            } else if (d.running && d.url) {
                tstate.dataset.state = 'ok';
                tlabel.textContent = '✓ tunnel online';
                tu.textContent = d.url;
                urlBox.style.display = '';
                startBtn.disabled = false;
                stopBtn.style.display = '';
                setCtaMode('regenerate');
            } else {
                tstate.dataset.state = 'idle';
                tlabel.textContent = i18n('setup.tunnelNotStarted', 'Not started yet.');
                urlBox.style.display = 'none';
                startBtn.disabled = false;
                stopBtn.style.display = 'none';
                setCtaMode('primary');
            }
        } catch {}
    }

    async function startTunnel() {
        const startBtn = $('#btn-start-tunnel');
        const tstate   = $('#tunnel-state');
        const tlabel   = $('#tunnel-state-label');
        const urlBox   = $('#tunnel-url-box');
        const tu       = $('#tunnel-url');

        startBtn.disabled = true;
        tstate.dataset.state = 'starting';
        tlabel.textContent = i18n('setup.tunnelStarting', 'Starting cloudflared…');
        urlBox.style.display = 'none';

        const port = parseInt($('#port').value, 10) || 9000;
        try {
            const r = await fetch('/api/wiz/setup/start-tunnel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ port }),
            });
            const d = await r.json();
            if (d.ok) {
                state.tunnelUrl = d.url;
                tu.textContent = d.url;
                urlBox.style.display = '';
                tstate.dataset.state = 'ok';
                tlabel.textContent = '✓ tunnel online';
                setCtaMode('regenerate');
                $('#btn-stop-tunnel').style.display = '';
            } else {
                tstate.dataset.state = 'err';
                const hint = d.install_hint ? ' — ' + d.install_hint.split('\n')[0] : '';
                tlabel.textContent = '⚠ ' + (d.error || 'failed') + hint;
            }
        } catch (e) {
            tstate.dataset.state = 'err';
            tlabel.textContent = '⚠ ' + String(e);
        } finally {
            startBtn.disabled = false;
        }
    }

    async function stopTunnel() {
        try { await fetch('/api/wiz/setup/stop-tunnel', { method: 'POST' }); } catch {}
        state.tunnelUrl = null;
        refreshTunnelStatus();
    }

    $('#btn-start-tunnel').addEventListener('click', startTunnel);
    $('#btn-stop-tunnel').addEventListener('click', stopTunnel);
    $('#btn-copy-tunnel').addEventListener('click', async () => {
        const u = $('#tunnel-url').textContent || '';
        try { await navigator.clipboard.writeText(u); } catch {}
    });
    $('#btn-back-3').addEventListener('click', () => showStep(3));
    $('#btn-next-3').addEventListener('click', () => {
        if (state.exposure === 'tunnel' && !state.tunnelUrl) {
            const tlabel = $('#tunnel-state-label');
            tlabel.textContent = i18n('setup.tunnelNeedsGen', 'Click "Generate tunnel" first, or go back and pick another option.');
            return;
        }
        if (state.exposure === 'manual') {
            const v = ($('#manual_public_url').value || '').trim();
            if (!v) { $('#manual_public_url').focus(); return; }
            state.manualUrl = v;
        }
        showStep(5);
    });

    // ── Step 5 — summary + SNS resolve + save ─────────────────────────
    async function resolveSns(force = false) {
        const sumBlock = $('#sns-summary');
        if (state.mode !== 'global') { sumBlock.style.display = 'none'; return; }
        sumBlock.style.display = '';
        const stat = $('#sns-status'), url = $('#sns-url'), pub = $('#sns-pubkey');
        stat.textContent = i18n('setup.snsResolving', 'Resolving…');
        stat.className = 'sns-status';
        url.textContent = '—';
        pub.textContent = '—';
        try {
            const r = await fetch('/api/wiz/setup/resolve-sns?domain=vortexx.sol'
                + (force ? '&t=' + Date.now() : ''));
            const d = await r.json();
            if (d.ok && d.url) {
                state.sns = { url: d.url, pubkey: d.pubkey || '' };
                url.textContent = d.url;
                pub.textContent = d.pubkey || '(none published)';
                stat.textContent = '✓ Resolved from on-chain SNS';
                stat.className = 'sns-status ok';
            } else {
                state.sns = null;
                stat.textContent = '⚠ ' + (d.error || 'no URL record yet');
                stat.className = 'sns-status err';
            }
        } catch (e) {
            state.sns = null;
            stat.textContent = '⚠ ' + String(e);
            stat.className = 'sns-status err';
        }
    }

    function renderSummary() {
        const sum = $('#summary');
        while (sum.firstChild) sum.removeChild(sum.firstChild);
        const row = (k, v, mono) => {
            const r = document.createElement('div');
            r.className = 'card-row';
            const a = document.createElement('span'); a.textContent = k;
            const b = mono ? document.createElement('code') : document.createElement('span');
            b.textContent = v || '—';
            r.appendChild(a); r.appendChild(b);
            return r;
        };
        sum.appendChild(row(i18n('setup.deviceName', 'Device name'), $('#device_name').value.trim()));
        sum.appendChild(row(i18n('setup.networkMode', 'Network mode'), state.mode));
        sum.appendChild(row(i18n('setup.port', 'Port'), $('#port').value));
        if (state.walletPubkey) {
            sum.appendChild(row(i18n('setup.walletAddr', 'Wallet (Solana)'),
                state.walletPubkey, true));
        }

        if (state.mode === 'custom') {
            sum.appendChild(row(i18n('setup.controllerUrl', 'Controller URL'), $('#controller_url').value.trim(), true));
            const pk = $('#controller_pubkey').value.trim();
            sum.appendChild(row(i18n('setup.controllerPubkey', 'Controller pubkey'),
                pk ? pk.slice(0, 16) + '…' : '—', true));
        }
        if (state.mode !== 'local') {
            let expText = state.exposure;
            if (state.exposure === 'tunnel') expText = '⚡ Cloudflare tunnel';
            else if (state.exposure === 'manual') expText = '⚙ Manual URL';
            else if (state.exposure === 'skip') expText = '⏭ Skipped';
            sum.appendChild(row(i18n('setup.exposure', 'Public exposure'), expText));

            const url = state.exposure === 'tunnel' ? state.tunnelUrl
                      : state.exposure === 'manual' ? state.manualUrl
                      : '';
            if (url) sum.appendChild(row(i18n('setup.publicUrl', 'Public URL'), url, true));
        }

        if (state.mode === 'global') resolveSns();
    }

    $('#btn-refresh-sns').addEventListener('click', () => resolveSns(true));
    $('#btn-back-4').addEventListener('click', () => {
        // Back from Review: local skips directly from device (step 2)
        // to review; global/custom came through the detail page (step 4).
        if (state.mode === 'local') showStep(2); else showStep(4);
    });

    async function save() {
        const btn = $('#btn-save');
        btn.disabled = true;
        const orig = btn.textContent;
        btn.textContent = i18n('setup.saving', 'Saving…');

        let ctrlUrl = '', ctrlPubkey = '';
        if (state.mode === 'global') {
            if (!state.sns || !state.sns.url) {
                showMsg(i18n('setup.snsNotResolved', 'vortexx.sol is not resolvable yet. Refresh or pick Custom.'), 'err');
                btn.disabled = false; btn.textContent = orig; return;
            }
            ctrlUrl = state.sns.url;
            ctrlPubkey = state.sns.pubkey || '';
        } else if (state.mode === 'custom') {
            ctrlUrl = $('#controller_url').value.trim();
            ctrlPubkey = $('#controller_pubkey').value.trim();
        }

        let announce = '';
        if (state.exposure === 'tunnel' && state.tunnelUrl) announce = state.tunnelUrl;
        else if (state.exposure === 'manual' && state.manualUrl) announce = state.manualUrl;

        if (!state.mnemonic) {
            showMsg(i18n('setup.seedMissing', 'Identity phrase missing — restart setup.'), 'err');
            btn.disabled = false; btn.textContent = orig; return;
        }

        const body = {
            device_name: $('#device_name').value.trim(),
            port: parseInt($('#port').value, 10) || 9000,
            network_mode: state.mode,
            controller_url: ctrlUrl,
            controller_pubkey: ctrlPubkey,
            announce_endpoints: announce,
            mnemonic: state.mnemonic,
        };

        try {
            const r = await fetch('/api/wiz/setup/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify(body),
            });
            const text = await r.text();
            let d = null;
            try { d = JSON.parse(text); } catch {}
            if (!r.ok) {
                const detail = d && d.detail ? (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail)) : text.slice(0, 200);
                showMsg('Server error ' + r.status + ': ' + detail, 'err');
                return;
            }
            if (!d) { showMsg('Bad response: ' + text.slice(0, 200), 'err'); return; }
            if (d.ok) {
                showMsg(i18n('setup.saved', 'Saved ✓ — opening admin dashboard…'), 'ok');
                // Poll /mode until the server confirms it's flipped to
                // admin, then do a cache-busting replace. Replaces the
                // previous brittle fixed-delay approach — no more "first
                // step looks like it reappeared" if fsync is slow.
                const waitForAdmin = async () => {
                    for (let i = 0; i < 20; i++) {
                        try {
                            const mr = await fetch('/mode', { cache: 'no-store' });
                            const md = await mr.json();
                            if (md.mode === 'admin') return true;
                        } catch (_) {}
                        await new Promise(r => setTimeout(r, 200));
                    }
                    return false;
                };
                waitForAdmin().then(ok => {
                    // location.replace avoids a history entry pointing at
                    // a now-dead setup URL. The ?v=Date.now() query busts
                    // any intermediate cache (service worker, proxy).
                    window.location.replace('/?v=' + Date.now());
                });
            } else {
                showMsg(d.error || 'Error', 'err');
            }
        } catch (e) {
            showMsg(i18n('setup.networkError', 'Network error: ') + String(e), 'err');
        } finally {
            btn.disabled = false;
            btn.textContent = orig;
        }
    }
    $('#btn-save').addEventListener('click', save);

    // First render — identity is step 1, the active one on load
    state.step = 1;
    renderDots();
})();
