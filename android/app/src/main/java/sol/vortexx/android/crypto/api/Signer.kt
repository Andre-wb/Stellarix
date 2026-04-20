package sol.vortexx.android.crypto.api

/**
 * Digital signature over a detached message (Ed25519 by default).
 *
 * Two operations only — sign and verify. Key generation stays here too
 * because the curve + encoding are implementation-private (Ed25519 uses
 * raw 32/32, ECDSA would be DER, etc.).
 */
interface Signer {
    fun generateKeyPair(): KeyPair
    fun sign(privateKey: ByteArray, message: ByteArray): ByteArray
    fun verify(publicKey: ByteArray, message: ByteArray, signature: ByteArray): Boolean
}
