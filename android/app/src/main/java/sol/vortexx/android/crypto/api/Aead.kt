package sol.vortexx.android.crypto.api

/**
 * Authenticated Encryption with Associated Data.
 *
 * Single responsibility: transform plaintext ↔ packed ciphertext under a
 * symmetric key. The wire format (`nonce || ciphertext || tag`) is fixed
 * across implementations so swapping AES-GCM for ChaCha20-Poly1305 later
 * only touches the impl, never the caller — matches the Vortex server's
 * `ciphertext_hex = nonce(12) + ct + tag(16)` format.
 */
interface Aead {
    /** Encrypt `plaintext` returning `nonce || ciphertext || tag`. */
    fun encrypt(key: ByteArray, plaintext: ByteArray, aad: ByteArray = EMPTY_AAD): ByteArray

    /**
     * Decrypt a `nonce || ciphertext || tag` blob produced by [encrypt].
     *
     * @throws AeadAuthenticationException if the tag does not verify.
     */
    fun decrypt(key: ByteArray, packed: ByteArray, aad: ByteArray = EMPTY_AAD): ByteArray

    companion object { val EMPTY_AAD: ByteArray = ByteArray(0) }
}

class AeadAuthenticationException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)
