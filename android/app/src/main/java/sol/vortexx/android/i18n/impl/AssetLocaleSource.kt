package sol.vortexx.android.i18n.impl

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import sol.vortexx.android.i18n.api.LocaleSource
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

private val Context.localePrefs by preferencesDataStore(name = "locale_prefs")
private val KEY_LOCALE = stringPreferencesKey("locale")

/**
 * 146-language loader. Locale JSON files live in `assets/locales/<code>.json`
 * — same shape as the web client's `/static/locales/*`. Lookup is:
 *   1. dotted path split ("nav.nodes" → ["nav", "nodes"])
 *   2. traverse nested JsonObject
 *   3. fall back to the en bundle if the key is missing
 *   4. if en is also missing, return the key itself so the UI is obvious
 *
 * Values are pre-parsed into a flat `Map<String, String>` on locale switch
 * so `translate()` stays O(1) — Compose recomposes many of them per frame.
 */
@Singleton
class AssetLocaleSource @Inject constructor(
    @ApplicationContext private val ctx: Context,
) : LocaleSource {

    private val json = Json { ignoreUnknownKeys = true }
    private val cache: MutableMap<String, Map<String, String>> = mutableMapOf()

    override val current: Flow<String> = ctx.localePrefs.data.map {
        it[KEY_LOCALE] ?: pickDeviceDefault()
    }

    override suspend fun setLocale(code: String) {
        ctx.localePrefs.edit { it[KEY_LOCALE] = code }
    }

    override suspend fun translate(key: String): String {
        val code = current.first()
        val bundle = loadBundle(code)
        bundle[key]?.let { return it }
        if (code != "en") loadBundle("en")[key]?.let { return it }
        return key
    }

    // ── internals ──────────────────────────────────────────────────────

    private fun loadBundle(code: String): Map<String, String> {
        cache[code]?.let { return it }
        val filename = "locales/$code.json"
        val flat = runCatching {
            ctx.assets.open(filename).bufferedReader().use {
                val obj = json.parseToJsonElement(it.readText()).jsonObject
                flatten(obj, prefix = "")
            }
        }.getOrDefault(emptyMap())
        cache[code] = flat
        return flat
    }

    private fun flatten(obj: JsonObject, prefix: String): Map<String, String> {
        val out = mutableMapOf<String, String>()
        for ((k, v) in obj) {
            val path = if (prefix.isEmpty()) k else "$prefix.$k"
            when (v) {
                is JsonObject -> out += flatten(v, path)
                else -> runCatching { out[path] = v.jsonPrimitive.content }
            }
        }
        return out
    }

    private fun pickDeviceDefault(): String {
        val lang = Locale.getDefault().language.lowercase()
        val country = Locale.getDefault().country.uppercase()
        return when {
            lang == "zh" && country == "TW" -> "zh-TW"
            lang.isNotBlank() -> lang
            else -> "en"
        }
    }
}
