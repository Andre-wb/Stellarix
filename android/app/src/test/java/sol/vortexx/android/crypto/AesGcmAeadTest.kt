package sol.vortexx.android.crypto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import sol.vortexx.android.crypto.api.AeadAuthenticationException
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.impl.AesGcmAead
import sol.vortexx.android.crypto.impl.SystemSecureRandom

/**
 * Round-trip + authentication failure. We don't pin a NIST ciphertext
 * vector because the wire format here is `nonce || ct || tag` with a
 * random nonce — per-encryption output is non-deterministic by design.
 */
class AesGcmAeadTest {

    private val random: SecureRandomProvider = SystemSecureRandom()
    private val aead = AesGcmAead(random)

    @Test fun `encrypt then decrypt round-trips`() {
        val key = ByteArray(32) { it.toByte() }
        val pt  = "hello vortex".toByteArray()
        val packed = aead.encrypt(key, pt)
        val out    = aead.decrypt(key, packed)
        assertArrayEquals(pt, out)
    }

    @Test fun `AAD must match on decrypt`() {
        val key = ByteArray(32)
        val pt  = "test".toByteArray()
        val packed = aead.encrypt(key, pt, aad = "room42".toByteArray())
        assertThrows(AeadAuthenticationException::class.java) {
            aead.decrypt(key, packed, aad = "room99".toByteArray())
        }
    }

    @Test fun `bit flip in ciphertext is detected`() {
        val key = ByteArray(32)
        val packed = aead.encrypt(key, "data".toByteArray())
        packed[packed.size - 1] = (packed[packed.size - 1].toInt() xor 0x01).toByte()
        assertThrows(AeadAuthenticationException::class.java) {
            aead.decrypt(key, packed)
        }
    }
}
