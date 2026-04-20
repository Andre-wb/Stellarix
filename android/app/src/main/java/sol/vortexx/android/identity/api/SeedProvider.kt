package sol.vortexx.android.identity.api

/**
 * 24-word BIP39 mnemonic source. Split from [IdentityRepository] so that:
 *   - wave 6 only generates; wave 20 adds import / restore without changing
 *     consumers
 *   - tests can deterministically inject a known mnemonic
 */
interface SeedProvider {
    fun generate(): Mnemonic
    fun toSeed(mnemonic: Mnemonic, passphrase: CharArray = CharArray(0)): ByteArray
}

@JvmInline
value class Mnemonic(val words: List<String>) {
    init { require(words.size == 24) { "BIP39 mnemonic must be 24 words (got ${words.size})" } }
    override fun toString(): String = words.joinToString(" ")
}
