package sol.vortexx.android.identity.impl

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import sol.vortexx.android.R
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Loads the BIP39 English wordlist (2048 words) from `res/raw/bip39_english`.
 *
 * Shipping a canonical wordlist as a raw resource keeps this repo free of
 * a 12 kB string literal committed in source — and makes the file easy
 * to diff against upstream without the noise of Kotlin array syntax.
 *
 * The file is fetched at build time (see scripts/fetch-bip39.sh in Wave 6's
 * README note). Access is idempotent and cached in a `Lazy`.
 */
@Singleton
class Bip39WordlistLoader @Inject constructor(
    @ApplicationContext private val ctx: Context,
) {
    val words: List<String> by lazy(LazyThreadSafetyMode.PUBLICATION) {
        ctx.resources.openRawResource(R.raw.bip39_english)
            .bufferedReader().use { it.readLines() }
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .also {
                check(it.size == 2048) {
                    "BIP39 wordlist must contain exactly 2048 words (got ${it.size})"
                }
            }
    }
}

