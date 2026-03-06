// static/js/crypto.js
// ============================================================================
// E2E криптография: ECIES (X25519 + HKDF + AES-256-GCM) для ключей комнат.
// Приватный ключ хранится как JWK JSON-строка (Web Crypto не позволяет
// экспортировать X25519 private key как 'raw').
// ============================================================================

const toHex   = b => Array.from(new Uint8Array(b)).map(x => x.toString(16).padStart(2,'0')).join('');
const fromHex = h => Uint8Array.from(h.match(/.{2}/g).map(b => parseInt(b, 16)));

/**
 * Шифрует roomKey для получателя через ECIES (X25519 + HKDF + AES-GCM).
 * @param {Uint8Array} roomKeyBytes - 32-байтный ключ комнаты
 * @param {string} recipientPubHex - X25519 публичный ключ получателя (hex)
 * @returns {Promise<{ephemeral_pub: string, ciphertext: string}>}
 */
export async function eciesEncrypt(roomKeyBytes, recipientPubHex) {
    // Эфемерная X25519 пара (новая для каждого шифрования — forward secrecy)
    const ephPair = await crypto.subtle.generateKey(
        { name: 'X25519' }, true, ['deriveBits']
    );
    const ephPubRaw = await crypto.subtle.exportKey('raw', ephPair.publicKey);

    // Импортируем публичный ключ получателя
    const recipientPub = await crypto.subtle.importKey(
        'raw', fromHex(recipientPubHex), { name: 'X25519' }, false, []
    );

    // X25519 DH → shared secret
    const sharedBits = await crypto.subtle.deriveBits(
        { name: 'X25519', public: recipientPub },
        ephPair.privateKey, 256
    );

    // HKDF-SHA256(shared, salt=ephPub, info="ecies-room-key") → ключ AES
    const hkdfKey = await crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey']);
    const encKey  = await crypto.subtle.deriveKey(
        { name: 'HKDF', hash: 'SHA-256', salt: ephPubRaw, info: new TextEncoder().encode('ecies-room-key') },
        hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt']
    );

    // AES-256-GCM шифрование
    const nonce      = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, encKey, roomKeyBytes);

    return {
        ephemeral_pub: toHex(ephPubRaw),
        ciphertext:    toHex(nonce) + toHex(ciphertext),
    };
}

/**
 * Расшифровывает ключ комнаты через ECIES.
 * @param {string} ephemeralPubHex - эфемерный публичный ключ (hex)
 * @param {string} ciphertextHex   - зашифрованные данные (hex)
 * @param {string} ourPrivKeyJwk   - приватный ключ как JWK JSON-строка
 * @returns {Promise<Uint8Array>} - расшифрованный ключ комнаты (32 байта)
 */
export async function eciesDecrypt(ephemeralPubHex, ciphertextHex, ourPrivKeyJwk) {
    const ephPubRaw = fromHex(ephemeralPubHex);

    // Импортируем эфемерный публичный ключ
    const ephPub = await crypto.subtle.importKey(
        'raw', ephPubRaw, { name: 'X25519' }, false, []
    );

    // Импортируем наш приватный ключ из JWK (не raw — X25519 так не работает)
    const ourPriv = await crypto.subtle.importKey(
        'jwk', JSON.parse(ourPrivKeyJwk), { name: 'X25519' }, false, ['deriveBits']
    );

    // X25519 DH → shared secret
    const sharedBits = await crypto.subtle.deriveBits(
        { name: 'X25519', public: ephPub }, ourPriv, 256
    );

    // HKDF → ключ AES
    const hkdfKey = await crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey']);
    const encKey  = await crypto.subtle.deriveKey(
        { name: 'HKDF', hash: 'SHA-256', salt: ephPubRaw, info: new TextEncoder().encode('ecies-room-key') },
        hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['decrypt']
    );

    // AES-256-GCM расшифровка
    const ctBytes = fromHex(ciphertextHex);
    const nonce   = ctBytes.slice(0, 12);
    const ct      = ctBytes.slice(12);
    const roomKey = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, encKey, ct);
    return new Uint8Array(roomKey);
}

// ============================================================================
// Хранилище ключей комнат в памяти (roomId → Uint8Array)
// ============================================================================

const _roomKeys = {};

export function getRoomKey(roomId)           { return _roomKeys[roomId] || null; }
export function setRoomKey(roomId, keyBytes) { _roomKeys[roomId] = keyBytes; }