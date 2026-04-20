package sol.vortexx.android.crypto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import sol.vortexx.android.crypto.impl.Ed25519Signer
import sol.vortexx.android.crypto.impl.SystemSecureRandom
import sol.vortexx.android.crypto.util.Hex

/**
 * RFC 8032 §7.1, Test 1 — empty message, fixed secret, deterministic sig.
 */
class Ed25519SignerTest {

    private val signer = Ed25519Signer(SystemSecureRandom())

    @Test fun `RFC 8032 test-1 sign-verify`() {
        val sk  = Hex.decode("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        val pk  = Hex.decode("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        val msg = ByteArray(0)
        val expected = Hex.decode(
            "e5564300c360ac729086e2cc806e828a" +
            "84877f1eb8e5d974d873e065224901555" +
            "fb8821590a33bacc61e39701cf9b46bd" +
            "25bf5f0595bdfa987f990b6ec5b5a00"
        )

        val sig = signer.sign(sk, msg)
        assertArrayEquals(expected, sig)
        assertTrue(signer.verify(pk, msg, sig))
    }

    @Test fun `verify rejects tampered signature`() {
        val kp = signer.generateKeyPair()
        val msg = "hello".toByteArray()
        val sig = signer.sign(kp.privateKey, msg)
        sig[0] = (sig[0].toInt() xor 0x01).toByte()
        assertFalse(signer.verify(kp.publicKey, msg, sig))
    }
}
