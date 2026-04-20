package sol.vortexx.android.crypto.impl

import sol.vortexx.android.crypto.api.Kdf
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import javax.inject.Inject
import javax.inject.Singleton

/**
 * HKDF-SHA256 — RFC 5869. Stateless, side-effect-free, so `@Singleton` is
 * a pure micro-optimization (one allocated Mac-instance creator reused).
 */
@Singleton
class HkdfSha256 @Inject constructor() : Kdf {

    override fun derive(ikm: ByteArray, salt: ByteArray, info: ByteArray, length: Int): ByteArray {
        require(length in 1..MAX_OUT) { "length out of range [1, $MAX_OUT]" }
        val prk = extract(ikm, salt)
        return expand(prk, info, length)
    }

    /** HKDF-Extract: PRK = HMAC(salt, IKM).  An all-zero salt is used when none given. */
    private fun extract(ikm: ByteArray, salt: ByteArray): ByteArray {
        val effectiveSalt = if (salt.isEmpty()) ByteArray(HASH_LEN) else salt
        return hmac(effectiveSalt, ikm)
    }

    /** HKDF-Expand: T(1) = HMAC(PRK, info || 0x01), T(n) = HMAC(PRK, T(n-1) || info || n). */
    private fun expand(prk: ByteArray, info: ByteArray, length: Int): ByteArray {
        val n = (length + HASH_LEN - 1) / HASH_LEN
        val out = ByteArray(length)
        var prev = ByteArray(0)
        var offset = 0
        for (i in 1..n) {
            val mac = Mac.getInstance(HMAC).apply { init(SecretKeySpec(prk, HMAC)) }
            mac.update(prev)
            if (info.isNotEmpty()) mac.update(info)
            mac.update(i.toByte())
            prev = mac.doFinal()
            val take = minOf(HASH_LEN, length - offset)
            System.arraycopy(prev, 0, out, offset, take)
            offset += take
        }
        return out
    }

    private fun hmac(key: ByteArray, msg: ByteArray): ByteArray {
        val mac = Mac.getInstance(HMAC).apply { init(SecretKeySpec(key, HMAC)) }
        return mac.doFinal(msg)
    }

    private companion object {
        const val HMAC     = "HmacSHA256"
        const val HASH_LEN = 32
        const val MAX_OUT  = 255 * HASH_LEN
    }
}
