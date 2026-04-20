package sol.vortexx.android.crypto

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import sol.vortexx.android.crypto.api.Argon2Params
import sol.vortexx.android.crypto.impl.Argon2idHasher

/**
 * We keep iteration / memory low for unit tests (deliberately far below
 * production defaults) so the suite stays fast on CI.  Production values
 * come from [Argon2Params.interactive] / [Argon2Params.sensitive].
 */
class Argon2idHasherTest {

    private val hasher = Argon2idHasher()
    private val cheap  = Argon2Params(iterations = 1, memoryKb = 1024, parallelism = 1, hashLen = 32)

    @Test fun `verify accepts matching password`() {
        val salt = ByteArray(16) { 0xaa.toByte() }
        val hash = hasher.hash("correct horse battery staple".toCharArray(), salt, cheap)
        assertTrue(hasher.verify("correct horse battery staple".toCharArray(), salt, hash, cheap))
    }

    @Test fun `verify rejects wrong password`() {
        val salt = ByteArray(16)
        val hash = hasher.hash("secret".toCharArray(), salt, cheap)
        assertFalse(hasher.verify("SECRET".toCharArray(), salt, hash, cheap))
    }

    @Test fun `different salts yield different hashes`() {
        val h1 = hasher.hash("pw".toCharArray(), ByteArray(16) { 0 }, cheap)
        val h2 = hasher.hash("pw".toCharArray(), ByteArray(16) { 1 }, cheap)
        assertFalse(h1.contentEquals(h2))
    }
}
