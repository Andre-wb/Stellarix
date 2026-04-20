package sol.vortexx.android.crypto.api

/**
 * Password-based key derivation / verification (Argon2id by default).
 *
 * `password: CharArray` because callers zero it after use — `String` in
 * Kotlin is interned and immutable, making secure wipe impossible.
 */
interface PasswordHasher {
    fun hash(
        password: CharArray,
        salt: ByteArray,
        params: Argon2Params = Argon2Params.interactive(),
    ): ByteArray

    /** Constant-time compare against `expected`. */
    fun verify(
        password: CharArray,
        salt: ByteArray,
        expected: ByteArray,
        params: Argon2Params = Argon2Params.interactive(),
    ): Boolean
}
