package sol.vortexx.android.crypto.api

/**
 * Thin value types for keys and signatures. Kept as data classes with raw
 * byte arrays so callers can interop with network payloads / hex encodings
 * without an adapter layer. equals/hashCode on ByteArray-carrying data
 * classes is reference-based — we override where ordering/hashing matters.
 */
data class KeyPair(val privateKey: ByteArray, val publicKey: ByteArray) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        return other is KeyPair
            && privateKey.contentEquals(other.privateKey)
            && publicKey.contentEquals(other.publicKey)
    }
    override fun hashCode(): Int =
        31 * privateKey.contentHashCode() + publicKey.contentHashCode()
}

/**
 * Argon2id tuning knobs. Defaults match OWASP 2024 guidance for interactive
 * logins (64 MiB, 3 passes, 1 thread, 32-byte tag) — ~150 ms on a modern
 * phone. Use `sensitive()` for key-derivation from a seed phrase.
 */
data class Argon2Params(
    val iterations: Int,
    val memoryKb: Int,
    val parallelism: Int,
    val hashLen: Int,
) {
    companion object {
        fun interactive() = Argon2Params(iterations = 3, memoryKb = 65_536, parallelism = 1, hashLen = 32)
        fun sensitive()   = Argon2Params(iterations = 4, memoryKb = 131_072, parallelism = 1, hashLen = 32)
    }
}
