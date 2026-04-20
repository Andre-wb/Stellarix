package sol.vortexx.android.crypto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.impl.SystemSecureRandom
import sol.vortexx.android.crypto.impl.X25519KeyAgreement
import sol.vortexx.android.crypto.util.Hex

/**
 * RFC 7748 §5.2 — Alice/Bob shared-secret vector.
 */
class X25519KeyAgreementTest {

    private val random: SecureRandomProvider = SystemSecureRandom()
    private val ka = X25519KeyAgreement(random)

    @Test fun `RFC 7748 alice-bob shared secret`() {
        val alicePriv = Hex.decode("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
        val bobPub    = Hex.decode("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
        val expected  = Hex.decode("4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742")

        val shared = ka.agree(alicePriv, bobPub)
        assertArrayEquals(expected, shared)
    }

    @Test fun `round-trip ECDH with two generated keypairs`() {
        val a = ka.generateKeyPair()
        val b = ka.generateKeyPair()
        val sAB = ka.agree(a.privateKey, b.publicKey)
        val sBA = ka.agree(b.privateKey, a.publicKey)
        assertEquals(32, sAB.size)
        assertArrayEquals(sAB, sBA)
    }
}
