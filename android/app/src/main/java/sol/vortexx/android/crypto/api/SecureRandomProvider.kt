package sol.vortexx.android.crypto.api

/**
 * Cryptographic entropy source. A thin wrapper so tests can inject a
 * deterministic impl (known-answer vectors) without touching the rest of
 * the crypto stack — and so platform SecureRandom can be swapped for a
 * hardware-backed one on Tegra / Titan M2 devices in a later wave.
 */
interface SecureRandomProvider {
    fun nextBytes(length: Int): ByteArray
}
