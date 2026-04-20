package sol.vortexx.android.crypto

import org.junit.Assert.assertArrayEquals
import org.junit.Test
import sol.vortexx.android.crypto.impl.HkdfSha256
import sol.vortexx.android.crypto.util.Hex

/**
 * RFC 5869 §A.1 (Test Case 1) — SHA-256, 22/13/10/42.
 * Independent from BouncyCastle: this Hkdf impl is pure JCE + Mac.
 */
class HkdfSha256Test {

    private val kdf = HkdfSha256()

    @Test fun `derives RFC 5869 test case 1`() {
        val ikm  = Hex.decode("0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b")
        val salt = Hex.decode("000102030405060708090a0b0c")
        val info = Hex.decode("f0f1f2f3f4f5f6f7f8f9")
        val okm  = Hex.decode(
            "3cb25f25faacd57a90434f64d0362f2a" +
            "2d2d0a90cf1a5a4c5db02d56ecc4c5bf" +
            "34007208d5b887185865"
        )

        val got = kdf.derive(ikm = ikm, salt = salt, info = info, length = 42)
        assertArrayEquals(okm, got)
    }
}
