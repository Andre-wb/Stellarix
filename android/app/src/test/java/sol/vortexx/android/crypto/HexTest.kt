package sol.vortexx.android.crypto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import sol.vortexx.android.crypto.util.Hex

class HexTest {
    @Test fun `round trip`() {
        val bytes = byteArrayOf(0x00, 0x01, 0x7f, 0x80.toByte(), 0xff.toByte())
        val hex = Hex.encode(bytes)
        assertEquals("00017f80ff", hex)
        assertArrayEquals(bytes, Hex.decode(hex))
    }

    @Test(expected = IllegalArgumentException::class)
    fun `odd length rejected`() { Hex.decode("abc") }

    @Test(expected = IllegalArgumentException::class)
    fun `non-hex rejected`() { Hex.decode("zz") }
}
