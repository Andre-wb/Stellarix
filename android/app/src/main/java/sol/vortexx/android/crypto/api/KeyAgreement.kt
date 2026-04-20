package sol.vortexx.android.crypto.api

/**
 * Asymmetric key agreement (X25519 by default).
 *
 * Responsibility ends at producing a raw 32-byte shared secret from a
 * private / public key pair. HKDF or any other post-processing lives in
 * [Kdf] — that split keeps this interface swappable for Kyber / X448
 * without touching consumers.
 */
interface KeyAgreement {
    fun generateKeyPair(): KeyPair
    fun agree(myPrivate: ByteArray, theirPublic: ByteArray): ByteArray
}
