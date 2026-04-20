package sol.vortexx.android.crypto.impl

import sol.vortexx.android.crypto.api.SecureRandomProvider
import java.security.SecureRandom
import javax.inject.Inject
import javax.inject.Singleton

/**
 * [SecureRandomProvider] backed by [java.security.SecureRandom].
 *
 * Android's SecureRandom is seeded from /dev/urandom and is fork-safe on
 * Zygote — no special re-seed dance needed. Held as a singleton so the
 * underlying reseed buffer is reused across calls.
 */
@Singleton
class SystemSecureRandom @Inject constructor() : SecureRandomProvider {
    private val rng = SecureRandom()

    override fun nextBytes(length: Int): ByteArray {
        require(length >= 0) { "length must be non-negative" }
        if (length == 0) return ByteArray(0)
        return ByteArray(length).also(rng::nextBytes)
    }
}
