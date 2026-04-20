/*
 * Vortex Premium — self-contained purchase flow.
 *
 *   window.VortexPremium.open()                    → open modal
 *   window.VortexPremium.refreshStatus()           → re-check on-chain
 *   window.VortexPremium.isPremium                 → boolean, live
 *   window.VortexPremium.wallet                    → current connected pubkey
 *
 * Assumes @solana/web3.js is loaded globally as `solanaWeb3` (see
 * templates — we inject the CDN tag once on pages that need it).
 *
 * What this file does manually (no Anchor TS client — we don't ship
 * a bundler):
 *   1. Derives PDAs: config, subscription (per beneficiary)
 *   2. Builds the subscribe_tier instruction with Borsh-serialized args
 *      and the Anchor-style 8-byte discriminator
 *   3. Opens Phantom, asks the user to sign, confirms on-chain
 *   4. Hits /api/premium/refresh to bust the server cache
 *   5. Writes the wallet to the user profile (PUT /api/user/profile)
 *      so future logins resolve premium without re-asking
 */
(() => {
    'use strict';

    // ── Config ────────────────────────────────────────────────────────

    const PROGRAM_ID_B58 = '8iNKGfNtAwZY8VLnoxardTstm5FFSePR5mN7LUyH4TRR';
    const RPC_URL = 'https://api.mainnet-beta.solana.com';
    // Treasury address is fetched at purchase time from /api/premium/plans
    // — never hard-coded here so changing config.treasury doesn't require
    // a client release.

    // Discriminator = sha256("global:subscribe_tier")[:8]
    // Precomputed once here so we don't ship a JS sha256 library.
    const DISCRIMINATOR_SUBSCRIBE_TIER = new Uint8Array([
         44, 244, 185,  48,  83, 119, 253, 175,
    ]);

    // ── Lazy Web3.js getter ──────────────────────────────────────────

    function web3() {
        if (!window.solanaWeb3) {
            throw new Error(
                'Solana Web3.js not loaded. Add ' +
                '<script src="https://unpkg.com/@solana/web3.js@1/lib/index.iife.min.js"></script> ' +
                'before premium.js.',
            );
        }
        return window.solanaWeb3;
    }

    // ── State ────────────────────────────────────────────────────────

    const state = {
        wallet: null,                  // PublicKey
        walletAddress: null,           // base58 string
        isPremium: false,
        endTimestamp: 0,
        plans: null,
        treasury: null,
    };

    // ── API calls ────────────────────────────────────────────────────

    async function fetchPlans() {
        const r = await fetch('/api/premium/plans');
        if (!r.ok) throw new Error('failed to fetch plans');
        state.plans = await r.json();
        state.treasury = state.plans.treasury_hint || null;
        return state.plans;
    }

    async function fetchStatus(wallet) {
        if (!wallet) return null;
        const r = await fetch('/api/premium/status?wallet=' + encodeURIComponent(wallet));
        if (!r.ok) return null;
        const d = await r.json();
        state.isPremium = !!d.is_premium;
        state.endTimestamp = d.end_timestamp || 0;
        return d;
    }

    async function linkWalletToProfile(wallet) {
        // Signed-challenge flow: prove wallet ownership before the
        // server accepts the link. A bystander sniffing network
        // traffic can't replay this — the challenge is single-use.
        try {
            const cr = await fetch('/api/premium/challenge', {
                credentials: 'include',
            });
            if (!cr.ok) {
                // Not authenticated — silently skip; link will be
                // attempted again next time the user opens the modal.
                return;
            }
            const { challenge } = await cr.json();
            if (!challenge) return;

            // Phantom returns { signature: Uint8Array, publicKey }.
            // signMessage requires a Uint8Array input, not a base64 string.
            const challengeBytes = Uint8Array.from(atob(challenge), c => c.charCodeAt(0));
            const signed = await window.solana.signMessage(challengeBytes, 'utf8');
            // signature → base58
            const sigB58 = bs58Encode(signed.signature);

            const lr = await fetch('/api/premium/link-wallet', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wallet,
                    challenge,
                    signature_b58: sigB58,
                }),
            });
            if (!lr.ok) {
                const body = await lr.text();
                console.warn('[premium] link-wallet failed:', lr.status, body);
            }
        } catch (e) {
            console.warn('[premium] link failed:', e);
        }
    }

    // Base58 encoder — tiny, inlined to avoid pulling a library.
    function bs58Encode(bytes) {
        const alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
        let zeros = 0;
        while (zeros < bytes.length && bytes[zeros] === 0) zeros++;
        let num = BigInt(0);
        for (const b of bytes) num = (num << 8n) + BigInt(b);
        let out = '';
        while (num > 0n) {
            const rem = num % 58n;
            num = num / 58n;
            out = alphabet[Number(rem)] + out;
        }
        for (let i = 0; i < zeros; i++) out = alphabet[0] + out;
        return out;
    }

    async function refreshServerCache(wallet) {
        try {
            await fetch('/api/premium/refresh?wallet=' + encodeURIComponent(wallet), {
                method: 'POST',
            });
        } catch (_) {}
    }

    // ── Phantom connect ──────────────────────────────────────────────

    async function connectPhantom() {
        if (!window.solana || !window.solana.isPhantom) {
            throw new Error('Phantom wallet extension not detected');
        }
        const resp = await window.solana.connect();
        state.wallet = resp.publicKey;
        state.walletAddress = resp.publicKey.toBase58();
        return resp.publicKey;
    }

    // ── PDA derivation ───────────────────────────────────────────────

    async function derivePDA(seeds) {
        const { PublicKey } = web3();
        const programId = new PublicKey(PROGRAM_ID_B58);
        const [pda] = PublicKey.findProgramAddressSync(seeds, programId);
        return pda;
    }

    const textEncoder = new TextEncoder();
    const seed = s => textEncoder.encode(s);

    async function configPda() { return derivePDA([seed('config')]); }

    async function subscriptionPda(beneficiary) {
        const { PublicKey } = web3();
        const ben = typeof beneficiary === 'string'
            ? new PublicKey(beneficiary)
            : beneficiary;
        return derivePDA([seed('subscription'), ben.toBytes()]);
    }

    // ── Instruction builder ──────────────────────────────────────────

    function encodeInstructionData(tierU8, beneficiaryBytes) {
        // 8-byte discriminator + u8 tier + 32-byte Pubkey
        const buf = new Uint8Array(8 + 1 + 32);
        buf.set(DISCRIMINATOR_SUBSCRIBE_TIER, 0);
        buf[8] = tierU8 & 0xff;
        buf.set(beneficiaryBytes, 9);
        return buf;
    }

    async function buildSubscribeTierTx(tier, beneficiary) {
        const { PublicKey, Transaction, TransactionInstruction, SystemProgram } = web3();

        if (!state.treasury) throw new Error('treasury address not configured');
        if (!state.wallet)   throw new Error('wallet not connected');

        const beneficiaryPk = typeof beneficiary === 'string'
            ? new PublicKey(beneficiary)
            : beneficiary;

        const cfg = await configPda();
        const sub = await subscriptionPda(beneficiaryPk);
        const treasuryPk = new PublicKey(state.treasury);
        const programId = new PublicKey(PROGRAM_ID_B58);

        const ix = new TransactionInstruction({
            programId,
            keys: [
                { pubkey: cfg,              isSigner: false, isWritable: true  },
                { pubkey: sub,              isSigner: false, isWritable: true  },
                { pubkey: state.wallet,     isSigner: true,  isWritable: true  },
                { pubkey: treasuryPk,       isSigner: false, isWritable: true  },
                { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
            ],
            data: Buffer.from(encodeInstructionData(tier, beneficiaryPk.toBytes())),
        });

        return new Transaction().add(ix);
    }

    async function submitPurchase(tier, beneficiary) {
        const { Connection } = web3();
        const connection = new Connection(RPC_URL, 'confirmed');

        const tx = await buildSubscribeTierTx(tier, beneficiary);

        tx.feePayer = state.wallet;
        tx.recentBlockhash = (await connection.getLatestBlockhash('confirmed')).blockhash;

        const signed = await window.solana.signTransaction(tx);
        const sig = await connection.sendRawTransaction(signed.serialize(), {
            skipPreflight: false,
            preflightCommitment: 'confirmed',
        });
        await connection.confirmTransaction(sig, 'confirmed');
        return sig;
    }

    // ── UI ───────────────────────────────────────────────────────────

    function el(tag, opts) {
        const e = document.createElement(tag);
        if (opts) {
            if (opts.cls) e.className = opts.cls;
            if (opts.txt) e.textContent = opts.txt;
            if (opts.on) {
                for (const k in opts.on) e.addEventListener(k, opts.on[k]);
            }
            if (opts.attrs) {
                for (const k in opts.attrs) e.setAttribute(k, opts.attrs[k]);
            }
        }
        return e;
    }

    function closeModal() {
        const m = document.getElementById('vx-premium-modal');
        if (m) m.remove();
    }

    function showError(msg) {
        const m = document.getElementById('vx-premium-msg');
        if (m) {
            m.className = 'vx-premium-msg vx-err';
            m.textContent = '⚠ ' + msg;
        } else {
            alert(msg);
        }
    }

    function showSuccess(msg) {
        const m = document.getElementById('vx-premium-msg');
        if (m) {
            m.className = 'vx-premium-msg vx-ok';
            m.textContent = '✓ ' + msg;
        }
    }

    function renderModal() {
        closeModal();
        const overlay = el('div', { cls: 'vx-premium-overlay', attrs: { id: 'vx-premium-modal' } });
        const modal = el('div', { cls: 'vx-premium-modal' });

        // Header
        modal.appendChild(el('button', {
            cls: 'vx-premium-close', txt: '×',
            on: { click: closeModal },
            attrs: { 'aria-label': 'Close' },
        }));
        modal.appendChild(el('h2', { txt: 'Vortex Premium', cls: 'vx-premium-title' }));
        modal.appendChild(el('p', {
            cls: 'vx-premium-sub',
            txt: 'Unlock larger files, unlimited big groups, HD video and more — paid in SOL on-chain, no recurring charges.',
        }));

        // Wallet strip
        const walletBox = el('div', { cls: 'vx-premium-wallet' });
        if (!state.walletAddress) {
            walletBox.appendChild(el('button', {
                cls: 'vx-btn vx-btn-primary',
                txt: 'Connect Phantom',
                on: {
                    click: async () => {
                        try {
                            await connectPhantom();
                            await fetchStatus(state.walletAddress);
                            await linkWalletToProfile(state.walletAddress);
                            renderModal();
                        } catch (e) {
                            showError(e.message || String(e));
                        }
                    },
                },
            }));
        } else {
            const short = state.walletAddress.slice(0, 6) + '…' + state.walletAddress.slice(-6);
            walletBox.appendChild(el('span', { cls: 'vx-wallet-addr', txt: short }));
            if (state.isPremium && state.endTimestamp > 0) {
                const until = new Date(state.endTimestamp * 1000).toLocaleDateString();
                walletBox.appendChild(el('span', {
                    cls: 'vx-wallet-tag vx-tag-active', txt: 'Active until ' + until,
                }));
            } else {
                walletBox.appendChild(el('span', {
                    cls: 'vx-wallet-tag vx-tag-free', txt: 'Free tier',
                }));
            }
        }
        modal.appendChild(walletBox);

        // Gift toggle
        const giftRow = el('div', { cls: 'vx-premium-gift' });
        const giftCheckbox = el('input', { attrs: { type: 'checkbox', id: 'vx-gift-toggle' } });
        giftRow.appendChild(giftCheckbox);
        giftRow.appendChild(el('label', { attrs: { for: 'vx-gift-toggle' }, txt: 'Buy as a gift' }));
        const giftInput = el('input', {
            cls: 'vx-gift-input',
            attrs: { placeholder: "Recipient's Solana address", type: 'text' },
        });
        giftInput.style.display = 'none';
        giftCheckbox.addEventListener('change', () => {
            giftInput.style.display = giftCheckbox.checked ? '' : 'none';
        });
        giftRow.appendChild(giftInput);
        modal.appendChild(giftRow);

        // Plan cards
        const plansWrap = el('div', { cls: 'vx-premium-plans' });
        const plans = state.plans && state.plans.plans ? state.plans.plans : [];
        plans.forEach(p => {
            const card = el('div', { cls: 'vx-plan-card' });
            card.appendChild(el('div', { cls: 'vx-plan-label', txt: p.label }));
            card.appendChild(el('div', { cls: 'vx-plan-price', txt: '$' + p.usd }));
            card.appendChild(el('div', {
                cls: 'vx-plan-duration',
                txt: p.months + ' month' + (p.months === 1 ? '' : 's'),
            }));
            card.appendChild(el('div', {
                cls: 'vx-plan-sol',
                txt: (p.lamports / 1e9).toFixed(3) + ' SOL',
            }));

            const buyBtn = el('button', {
                cls: 'vx-btn vx-btn-buy',
                txt: 'Buy',
            });
            buyBtn.addEventListener('click', async () => {
                if (!state.walletAddress) {
                    showError('Connect your wallet first');
                    return;
                }
                const beneficiary = giftCheckbox.checked
                    ? giftInput.value.trim()
                    : state.walletAddress;
                if (!beneficiary) {
                    showError('Enter the recipient address');
                    return;
                }
                try {
                    buyBtn.disabled = true;
                    buyBtn.textContent = 'Signing…';
                    showSuccess('Waiting for Phantom signature…');
                    const sig = await submitPurchase(p.tier, beneficiary);
                    showSuccess('Paid — transaction ' + sig.slice(0, 16) + '…');
                    buyBtn.textContent = 'Paid ✓';
                    await refreshServerCache(beneficiary);
                    if (beneficiary === state.walletAddress) {
                        await fetchStatus(state.walletAddress);
                        renderModal();
                    }
                } catch (e) {
                    buyBtn.disabled = false;
                    buyBtn.textContent = 'Buy';
                    showError('Purchase failed: ' + (e.message || String(e)));
                }
            });
            card.appendChild(buyBtn);
            plansWrap.appendChild(card);
        });
        modal.appendChild(plansWrap);

        modal.appendChild(el('div', {
            cls: 'vx-premium-msg',
            attrs: { id: 'vx-premium-msg' },
        }));

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        overlay.appendChild(modal);
        document.body.appendChild(overlay);
    }

    // ── Public API ───────────────────────────────────────────────────

    async function open() {
        try {
            if (!state.plans) await fetchPlans();
            if (window.solana && window.solana.isPhantom
                && !state.walletAddress
                && window.solana.isConnected) {
                try {
                    const pk = window.solana.publicKey;
                    if (pk) {
                        state.wallet = pk;
                        state.walletAddress = pk.toBase58();
                        await fetchStatus(state.walletAddress);
                    }
                } catch (_) {}
            }
            renderModal();
        } catch (e) {
            alert('Vortex Premium: ' + (e.message || String(e)));
        }
    }

    async function refreshStatus() {
        if (state.walletAddress) {
            await refreshServerCache(state.walletAddress);
            return await fetchStatus(state.walletAddress);
        }
        return null;
    }

    window.VortexPremium = {
        open,
        refreshStatus,
        get isPremium()  { return state.isPremium; },
        get wallet()     { return state.walletAddress; },
        get endTimestamp() { return state.endTimestamp; },
    };
})();
