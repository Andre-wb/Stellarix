package sol.vortexx.android.crypto.util

/**
 * Lowercase hex codec matching Python's `bytes.hex()` / `bytes.fromhex()`.
 * Lives under crypto/util because every impl here reads/writes hex from
 * the wire; keeping a single codec avoids subtle case / prefix drift.
 */
object Hex {
    private const val DIGITS = "0123456789abcdef"

    fun encode(bytes: ByteArray): String {
        val out = CharArray(bytes.size * 2)
        for (i in bytes.indices) {
            val v = bytes[i].toInt() and 0xff
            out[i * 2]     = DIGITS[v ushr 4]
            out[i * 2 + 1] = DIGITS[v and 0x0f]
        }
        return String(out)
    }

    fun decode(hex: String): ByteArray {
        val s = hex.lowercase()
        require(s.length % 2 == 0) { "hex must have even length" }
        val out = ByteArray(s.length / 2)
        for (i in out.indices) {
            val hi = Character.digit(s[i * 2],     16)
            val lo = Character.digit(s[i * 2 + 1], 16)
            require(hi >= 0 && lo >= 0) { "non-hex character" }
            out[i] = ((hi shl 4) or lo).toByte()
        }
        return out
    }
}
