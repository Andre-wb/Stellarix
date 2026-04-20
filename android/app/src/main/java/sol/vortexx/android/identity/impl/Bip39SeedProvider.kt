package sol.vortexx.android.identity.impl

import org.bouncycastle.crypto.PBEParametersGenerator
import org.bouncycastle.crypto.digests.SHA256Digest
import org.bouncycastle.crypto.digests.SHA512Digest
import org.bouncycastle.crypto.generators.PKCS5S2ParametersGenerator
import org.bouncycastle.crypto.params.KeyParameter
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.identity.api.Mnemonic
import sol.vortexx.android.identity.api.SeedProvider
import java.text.Normalizer
import javax.inject.Inject
import javax.inject.Singleton

/**
 * BIP39 generator — 256 bits of entropy → 24 words from the English
 * wordlist → PBKDF2-HMAC-SHA512 with 2048 rounds to produce a 64-byte seed.
 *
 * We inline the wordlist rather than pulling in a BIP39 library — it's
 * 2048 strings (≈22 kB), stable for over a decade, and copying it lets
 * the crypto stack stay dep-free from yet another jar. The list lives
 * in its own file so this one reads top-to-bottom.
 */
@Singleton
class Bip39SeedProvider @Inject constructor(
    private val random: SecureRandomProvider,
    private val wordlist: Bip39WordlistLoader,
) : SeedProvider {

    override fun generate(): Mnemonic {
        // 256 bits of entropy ⇒ 24 words. We compute the checksum per spec:
        // first (entropy_bits / 32) = 8 bits of SHA-256(entropy) appended.
        val entropy = random.nextBytes(32)
        val digest = SHA256Digest()
        digest.update(entropy, 0, entropy.size)
        val hash = ByteArray(digest.digestSize).also { digest.doFinal(it, 0) }

        val bits = BooleanArray(entropy.size * 8 + 8)
        for (i in entropy.indices) {
            val b = entropy[i].toInt() and 0xff
            for (bit in 0..7) bits[i * 8 + bit] = (b ushr (7 - bit)) and 1 == 1
        }
        // Append checksum bits (first 8 bits of hash because we have 256 bits of entropy).
        val cs = hash[0].toInt() and 0xff
        for (bit in 0..7) bits[entropy.size * 8 + bit] = (cs ushr (7 - bit)) and 1 == 1

        val words = ArrayList<String>(24)
        for (i in 0 until 24) {
            var idx = 0
            for (bit in 0..10) {
                idx = (idx shl 1) or (if (bits[i * 11 + bit]) 1 else 0)
            }
            words += wordlist.words[idx]
        }
        return Mnemonic(words)
    }

    override fun toSeed(mnemonic: Mnemonic, passphrase: CharArray): ByteArray {
        val mnemonicBytes = Normalizer.normalize(mnemonic.toString(), Normalizer.Form.NFKD)
            .toByteArray(Charsets.UTF_8)
        val salt = ("mnemonic" + String(passphrase)).let {
            Normalizer.normalize(it, Normalizer.Form.NFKD).toByteArray(Charsets.UTF_8)
        }
        val gen = PKCS5S2ParametersGenerator(SHA512Digest()).apply {
            init(mnemonicBytes, salt, 2048)
        }
        val keyParam = gen.generateDerivedMacParameters(64 * 8) as KeyParameter
        return keyParam.key
    }
}
