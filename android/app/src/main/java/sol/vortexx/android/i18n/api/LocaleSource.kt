package sol.vortexx.android.i18n.api

import kotlinx.coroutines.flow.Flow

/**
 * Wave 20 — 146-locale bundle loaded from assets, same JSON shape as the
 * web client's locales. A tiny Compose LocalProvider exposes a `t()`
 * function keyed by `"ns.key"` so messages can be migrated gradually.
 */
interface LocaleSource {
    val current: Flow<String>
    suspend fun setLocale(code: String)
    suspend fun translate(key: String): String
}
