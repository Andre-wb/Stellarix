/* Shared utilities for every page of the controller site.
 * Loads AFTER i18n.js — so window.VortexI18n is already available here.
 */
(() => {
    'use strict';

    // Mark the active nav link based on URL
    const path = location.pathname.replace(/\/+$/, '') || '/';
    const tab = path === '/' ? 'home'
              : path.startsWith('/nodes')    ? 'nodes'
              : path.startsWith('/entries')  ? 'entries'
              : path.startsWith('/mirrors')  ? 'mirrors'
              : path.startsWith('/security') ? 'security'
              : 'home';
    document.querySelectorAll('[data-nav]').forEach(a => {
        a.classList.toggle('active', a.dataset.nav === tab);
    });

    // ── Canonical JSON (server matches) ────────────────────────────────
    window.canonicalJson = obj => {
        if (obj === null || typeof obj !== 'object') return JSON.stringify(obj);
        if (Array.isArray(obj)) return '[' + obj.map(canonicalJson).join(',') + ']';
        const keys = Object.keys(obj).sort();
        return '{' + keys.map(k => JSON.stringify(k) + ':' + canonicalJson(obj[k])).join(',') + '}';
    };

    window.hexToBytes = hex => {
        if (!hex || hex.length % 2 !== 0) throw new Error('invalid hex');
        const out = new Uint8Array(hex.length / 2);
        for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
        return out;
    };

    let _cryptoSupported = null;

    window.verifyEnvelope = async (env, pubkeyHex) => {
        if (!pubkeyHex) return null;
        try {
            const pub = await crypto.subtle.importKey(
                'raw', hexToBytes(pubkeyHex),
                { name: 'Ed25519' }, false, ['verify'],
            );
            const data = new TextEncoder().encode(canonicalJson(env.payload));
            return await crypto.subtle.verify({ name: 'Ed25519' }, pub, hexToBytes(env.signature), data);
        } catch (e) {
            if (_cryptoSupported === null) {
                _cryptoSupported = false;
                console.warn('Ed25519 verify unavailable:', e);
            }
            return null;
        }
    };

    // ── Toast ──────────────────────────────────────────────────────────
    let toastEl;
    window.toast = msg => {
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.className = 'toast';
            document.body.appendChild(toastEl);
        }
        toastEl.textContent = msg;
        toastEl.classList.add('show');
        setTimeout(() => toastEl.classList.remove('show'), 1700);
    };

    window.copyText = async text => {
        try { await navigator.clipboard.writeText(text); toast('Copied'); }
        catch {
            const ta = document.createElement('textarea');
            ta.value = text; document.body.appendChild(ta); ta.select();
            document.execCommand('copy'); ta.remove(); toast('Copied');
        }
    };

    // Delegate copy clicks for [data-copy] buttons
    document.addEventListener('click', e => {
        const btn = e.target.closest('[data-copy]');
        if (!btn) return;
        const sel = btn.getAttribute('data-copy');
        if (sel === 'parent') {
            const parent = btn.closest('.item-card, .pubkey-box, .card-row');
            const text = parent && parent.querySelector('code');
            if (text) copyText(text.textContent || '');
        } else {
            const src = document.querySelector(sel);
            if (src) copyText((src.textContent || '').trim());
        }
    });

    // ── Time helpers ──────────────────────────────────────────────────
    window.ago = ts => {
        if (!ts) return '—';
        const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
        if (s < 60)     return s + 's ago';
        if (s < 3600)   return Math.floor(s / 60) + 'm ago';
        if (s < 86400)  return Math.floor(s / 3600) + 'h ago';
        if (s < 86400 * 30) return Math.floor(s / 86400) + 'd ago';
        return Math.floor(s / 86400 / 30) + 'mo ago';
    };

    window.shortKey = (hex, n = 8) => {
        if (!hex) return '—';
        if (hex.length <= n * 2 + 1) return hex;
        return hex.slice(0, n) + '…' + hex.slice(-6);
    };
})();
