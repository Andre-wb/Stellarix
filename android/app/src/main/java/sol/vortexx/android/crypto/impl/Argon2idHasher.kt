package sol.vortexx.android.crypto.impl

import org.bouncycastle.crypto.generators.Argon2BytesGenerator
import org.bouncycastle.crypto.params.Argon2Parameters
import sol.vortexx.android.crypto.api.Argon2Params
import sol.vortexx.android.crypto.api.PasswordHasher
import java.nio.CharBuffer
import java.nio.charset.StandardCharsets
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Argon2id — RFC 9106. Hash is derived deterministically from
 * (password, salt, params) so a stored hash can be re-verified without
 * separately recording iterations/memory (the caller persists [Argon2Params]
 * alongside the salt).
 *
 * Passwords arrive as CharArray and are zeroed after the UTF-8 round-trip.
 */
@Singleton
class Argon2idHasher @Inject constructor() : PasswordHasher {

    override fun hash(password: CharArray, salt: ByteArray, params: Argon2Params): ByteArray {
        val pwBytes = charArrayToUtf8(password)
        try {
            val p = Argon2Parameters.Builder(Argon2Parameters.ARGON2_id)
                .withVersion(Argon2Parameters.ARGON2_VERSION_13)
                .withSalt(salt)
                .withIterations(params.iterations)
                .withMemoryAsKB(params.memoryKb)
                .withParallelism(params.parallelism)
                .build()
            val gen = Argon2BytesGenerator().apply { init(p) }
            val out = ByteArray(params.hashLen)
            gen.generateBytes(pwBytes, out)
            return out
        } finally {
            pwBytes.fill(0)
        }
    }

    override fun verify(
        password: CharArray,
        salt: ByteArray,
        expected: ByteArray,
        params: Argon2Params,
    ): Boolean {
        val got = hash(password, salt, params)
        return constantTimeEquals(got, expected)
    }

    // ── internals ──────────────────────────────────────────────────────

    private fun charArrayToUtf8(chars: CharArray): ByteArray {
        // Don't go through String — that would pin an immutable copy in the
        // intern pool, defeating the point of accepting CharArray.
        val buf = StandardCharsets.UTF_8.encode(CharBuffer.wrap(chars))
        val out = ByteArray(buf.remaining()).also { buf.get(it) }
        return out
    }

    private fun constantTimeEquals(a: ByteArray, b: ByteArray): Boolean {
        if (a.size != b.size) return false
        var diff = 0
        for (i in a.indices) diff = diff or (a[i].toInt() xor b[i].toInt())
        return diff == 0
    }
}
