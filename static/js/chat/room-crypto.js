// static/js/chat/room-crypto.js — AES-256-GCM helpers + in-memory room key cache

export const toHex   = b => Array.from(new Uint8Array(b)).map(x => x.toString(16).padStart(2,'0')).join('');
export const fromHex = h => Uint8Array.from(h.match(/.{2}/g).map(b => parseInt(b, 16)));

// Room keys: primary store in JS heap, backed by sessionStorage for page reload survival.
const _roomKeyCache = new Map();

// ── Metadata padding ────────────────────────────────────────────────────
// Log-spaced bucket sizes matching app/chats/messages/padding.py + Rust
// vortex_chat.pad_to_bucket. Every outgoing ciphertext is padded to the
// next bucket so traffic analysis can't tell "ok" apart from "here's
// the link". Format of the padded PLAINTEXT (before AES-GCM):
//
//   [0x56 0x78 magic] [u16 BE plaintext_len] [plaintext bytes] [random fill]
//
// "V" + "X" magic lets a post-upgrade client tell padded vs legacy
// messages (decrypt-time), so old chat history keeps working.
const _BUCKETS = [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536];
const _PAD_MAGIC = 0x5678;   // BE bytes: 0x56 0x78 = 'V' 'x'

function _paddingEnabled() {
    // Respect a user-visible toggle; default ON. We read from a global
    // AppState.config which the app populates from /api/health at boot.
    try {
        const cfg = (window.AppState && window.AppState.config) || {};
        if (cfg.metadata_padding === false) return false;
    } catch (_) {}
    return true;
}

function _padPlaintext(plain /* Uint8Array */) {
    const n = plain.length;
    if (n > 65534) throw new Error('plaintext exceeds 64 KiB padding limit');
    const needed = n + 4;   // 2 magic + 2 length
    const bucket = _BUCKETS.find(b => b >= needed) || 65536;
    const out = new Uint8Array(bucket);
    // Magic
    out[0] = (_PAD_MAGIC >> 8) & 0xFF;
    out[1] =  _PAD_MAGIC       & 0xFF;
    // Length (BE u16)
    out[2] = (n >> 8) & 0xFF;
    out[3] =  n       & 0xFF;
    // Plaintext
    out.set(plain, 4);
    // Random fill past the plaintext
    const tail = out.subarray(4 + n);
    crypto.getRandomValues(tail);
    return out;
}

function _unpadPlaintext(padded /* Uint8Array */) {
    if (padded.length < 4) return padded;
    const magic = (padded[0] << 8) | padded[1];
    if (magic !== _PAD_MAGIC) {
        // Legacy unpadded message — return as-is for backward compat.
        return padded;
    }
    const n = (padded[2] << 8) | padded[3];
    if (4 + n > padded.length) {
        throw new Error('declared plaintext length exceeds padded buffer');
    }
    return padded.subarray(4, 4 + n);
}


export async function encryptText(text, roomKeyBytes) {
    const key = await crypto.subtle.importKey(
        'raw', roomKeyBytes, { name: 'AES-GCM' }, false, ['encrypt']
    );
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(text);
    // Pad before encrypt — ciphertext length reveals only the bucket,
    // not the original plaintext length.
    const plaintext = _paddingEnabled() ? _padPlaintext(encoded) : encoded;
    const ct = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv: nonce },
        key,
        plaintext
    );
    return toHex(nonce) + toHex(ct);
}

export async function decryptText(ciphertextHex, roomKeyBytes) {
    const raw   = fromHex(ciphertextHex);
    const nonce = raw.slice(0, 12);
    const ct    = raw.slice(12);
    const key   = await crypto.subtle.importKey(
        'raw', roomKeyBytes, { name: 'AES-GCM' }, false, ['decrypt']
    );
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, key, ct);
    // Unpad — backward-compatible: returns raw bytes if magic absent.
    const unpadded = _unpadPlaintext(new Uint8Array(plain));
    return new TextDecoder().decode(unpadded);
}

export function _saveRoomKeyToSession(roomId, keyBytes) {
    _roomKeyCache.set(String(roomId), keyBytes);
    // Backup to sessionStorage + localStorage so key survives page reload and browser restart
    try {
        const hex = toHex(keyBytes);
        sessionStorage.setItem(`vortex_rk_${roomId}`, hex);
        localStorage.setItem(`vortex_rk_${roomId}`, hex);
    } catch {}
}

export function _loadRoomKeyFromSession(roomId) {
    const cached = _roomKeyCache.get(String(roomId));
    if (cached) return cached;
    // Fallback: sessionStorage → localStorage (browser restart survival)
    try {
        const hex = sessionStorage.getItem(`vortex_rk_${roomId}`)
                 || localStorage.getItem(`vortex_rk_${roomId}`);
        if (hex) {
            const bytes = fromHex(hex);
            _roomKeyCache.set(String(roomId), bytes);
            return bytes;
        }
    } catch {}
    return null;
}

export function _clearRoomKeyFromSession(roomId) {
    _roomKeyCache.delete(String(roomId));
    try {
        sessionStorage.removeItem(`vortex_rk_${roomId}`);
        localStorage.removeItem(`vortex_rk_${roomId}`);
    } catch {}
}
