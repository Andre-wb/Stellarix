const E2E = (() => {
    const PRIV_JWK = 'e2ee_priv_jwk';
    const PUB_HEX = 'e2ee_pub_hex';
    const PEER_HEX = 'e2ee_peer_hex';
    const SESSION_HEX = 'e2ee_session_hex';
    const FINGERPRINT = 'e2ee_fingerprint';
    const SALT = 'stellarix-session-key-v1';
    const INFO = 'chat session key';
    const IV_LEN = 12;
    const TAG_LEN = 16;
    const MAX_PAYLOAD_LEN = 96;
    const MAX_PLAINTEXT_BYTES = MAX_PAYLOAD_LEN - IV_LEN - TAG_LEN;

    const enc = new TextEncoder();
    const dec = new TextDecoder();

    function bytesToHex(bytes) {
        return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    function hexToBytes(hex) {
        if (typeof hex !== 'string' || hex.length % 2 !== 0 || /[^0-9a-fA-F]/.test(hex)) {
            throw new Error('некорректный hex');
        }
        const out = new Uint8Array(hex.length / 2);
        for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
        return out;
    }

    async function generateKeypair() {
        const kp = await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits']);
        const rawPub = new Uint8Array(await crypto.subtle.exportKey('raw', kp.publicKey));
        const jwk = await crypto.subtle.exportKey('jwk', kp.privateKey);
        return { publicHex: bytesToHex(rawPub), privateJwk: jwk };
    }

    async function fingerprintOf(keyBytes) {
        const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', keyBytes));
        return bytesToHex(digest.subarray(0, 16));
    }

    async function deriveSessionKey(privateJwk, myPublicHex, peerPublicHex) {
        const priv = await crypto.subtle.importKey('jwk', privateJwk, { name: 'X25519' }, false, ['deriveBits']);
        const peerRaw = hexToBytes(peerPublicHex);
        if (peerRaw.length !== 32) throw new Error('публичный ключ собеседника должен быть 32 байта');
        const peerKey = await crypto.subtle.importKey('raw', peerRaw, { name: 'X25519' }, false, []);

        let sharedBuf;
        try {
            sharedBuf = await crypto.subtle.deriveBits({ name: 'X25519', public: peerKey }, priv, 256);
        } catch (e) {
            throw new Error('небезопасный публичный ключ собеседника');
        }
        const shared = new Uint8Array(sharedBuf);
        if (shared.every(b => b === 0)) throw new Error('небезопасный публичный ключ собеседника');

        const ordered = [bytesToHex(hexToBytes(myPublicHex)), bytesToHex(peerRaw)].sort();
        const info = enc.encode(INFO + '|' + ordered[0] + '|' + ordered[1]);

        const hk = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveBits']);
        const keyBuf = await crypto.subtle.deriveBits(
            { name: 'HKDF', hash: 'SHA-256', salt: enc.encode(SALT), info },
            hk,
            256
        );
        const keyBytes = new Uint8Array(keyBuf);
        const fingerprint = await fingerprintOf(keyBytes);
        return { keyHex: bytesToHex(keyBytes), fingerprint };
    }

    async function importAesKey(keyHex) {
        const keyBytes = hexToBytes(keyHex);
        if (keyBytes.length !== 32) throw new Error('повреждён сеансовый ключ');
        return crypto.subtle.importKey('raw', keyBytes, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
    }

    async function encryptWithKeyHex(keyHex, plaintext) {
        const ptBytes = enc.encode(plaintext);
        if (ptBytes.length === 0) throw new Error('сообщение не может быть пустым');
        if (ptBytes.length > MAX_PLAINTEXT_BYTES) {
            throw new Error('сообщение слишком длинное для одной передачи звуком (макс. ' +
                MAX_PLAINTEXT_BYTES + ' байт, у вас ' + ptBytes.length + ')');
        }
        const key = await importAesKey(keyHex);
        const iv = crypto.getRandomValues(new Uint8Array(IV_LEN));
        const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, ptBytes));
        const out = new Uint8Array(IV_LEN + ct.length);
        out.set(iv, 0);
        out.set(ct, IV_LEN);
        return bytesToHex(out);
    }

    async function decryptWithKeyHex(keyHex, payloadHex) {
        const data = hexToBytes(payloadHex);
        if (data.length < IV_LEN + TAG_LEN) throw new Error('сообщение слишком короткое — повреждено при передаче');
        const key = await importAesKey(keyHex);
        const iv = data.subarray(0, IV_LEN);
        const ct = data.subarray(IV_LEN);
        let ptBuf;
        try {
            ptBuf = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
        } catch (e) {
            throw new Error('не удалось расшифровать: неверный ключ или сообщение повреждено при передаче');
        }
        return dec.decode(ptBuf);
    }

    function isSupported() {
        return typeof crypto !== 'undefined' && !!crypto.subtle &&
            (typeof window === 'undefined' || window.isSecureContext);
    }

    async function ensureKeypair() {
        const pubHex = localStorage.getItem(PUB_HEX);
        const privJwk = localStorage.getItem(PRIV_JWK);
        if (pubHex && privJwk) return pubHex;
        const generated = await generateKeypair();
        localStorage.setItem(PUB_HEX, generated.publicHex);
        localStorage.setItem(PRIV_JWK, JSON.stringify(generated.privateJwk));
        return generated.publicHex;
    }

    async function completePairing(peerPublicHex) {
        const pubHex = localStorage.getItem(PUB_HEX);
        const privJwkStr = localStorage.getItem(PRIV_JWK);
        if (!pubHex || !privJwkStr) {
            throw new Error('сначала нажмите «Поделиться публичным ключом» на этом устройстве');
        }
        const derived = await deriveSessionKey(JSON.parse(privJwkStr), pubHex, peerPublicHex);
        localStorage.setItem(SESSION_HEX, derived.keyHex);
        localStorage.setItem(FINGERPRINT, derived.fingerprint);
        localStorage.setItem(PEER_HEX, peerPublicHex.toLowerCase());
        return derived.fingerprint;
    }

    function isPaired() {
        return !!localStorage.getItem(SESSION_HEX);
    }

    function getFingerprint() {
        return localStorage.getItem(FINGERPRINT) || '';
    }

    function getPublicHex() {
        return localStorage.getItem(PUB_HEX) || '';
    }

    function getPeerHex() {
        return localStorage.getItem(PEER_HEX) || '';
    }

    function hasKeypair() {
        return !!localStorage.getItem(PRIV_JWK) && !!localStorage.getItem(PUB_HEX);
    }

    function hasPendingKey() {
        return !!localStorage.getItem(PRIV_JWK) && !localStorage.getItem(SESSION_HEX);
    }

    function reset() {
        localStorage.removeItem(PRIV_JWK);
        localStorage.removeItem(PUB_HEX);
        localStorage.removeItem(PEER_HEX);
        localStorage.removeItem(SESSION_HEX);
        localStorage.removeItem(FINGERPRINT);
    }

    async function encrypt(plaintext) {
        const keyHex = localStorage.getItem(SESSION_HEX);
        if (!keyHex) throw new Error('сначала выполните сопряжение по звуку на странице «Сопряжение»');
        return encryptWithKeyHex(keyHex, plaintext);
    }

    async function decrypt(payloadHex) {
        const keyHex = localStorage.getItem(SESSION_HEX);
        if (!keyHex) throw new Error('сначала выполните сопряжение по звуку на странице «Сопряжение»');
        return decryptWithKeyHex(keyHex, payloadHex);
    }

    function getSessionKeyHex() {
        return localStorage.getItem(SESSION_HEX) || '';
    }

    return {
        MAX_PLAINTEXT_BYTES,
        isSupported,
        generateKeypair,
        deriveSessionKey,
        fingerprintOf,
        encryptWithKeyHex,
        decryptWithKeyHex,
        ensureKeypair,
        completePairing,
        isPaired,
        getFingerprint,
        getPublicHex,
        getPeerHex,
        hasKeypair,
        hasPendingKey,
        reset,
        encrypt,
        decrypt,
        getSessionKeyHex,
        bytesToHex,
        hexToBytes,
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = E2E;
}
