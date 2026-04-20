package sol.vortexx.android.crypto.api

/**
 * Key derivation function — HKDF-SHA256 per RFC 5869.
 *
 * Kept narrow on purpose: `derive(ikm, salt, info, len)`. Password-based
 * derivation is a different shape (adds memory/iteration knobs) and lives
 * in [PasswordHasher].
 */
interface Kdf {
    fun derive(
        ikm: ByteArray,
        salt: ByteArray = ByteArray(0),
        info: ByteArray = ByteArray(0),
        length: Int = 32,
    ): ByteArray
}
