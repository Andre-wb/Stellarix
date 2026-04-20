package sol.vortexx.android.settings.api

import kotlinx.coroutines.flow.Flow

/**
 * Wave 20 — user-visible preferences (theme, notifications, stealth
 * level, panic wipe). Splits cleanly from [sol.vortexx.android.bootstrap.api.NodePreferences]
 * (node URL) because the two have different backup semantics: settings
 * are personal, base URL is device-local.
 */
interface SettingsStore {
    val theme: Flow<String>                 // "system" | "dark" | "light"
    val notificationsEnabled: Flow<Boolean>

    suspend fun setTheme(mode: String)
    suspend fun setNotificationsEnabled(on: Boolean)
    suspend fun wipeAll()                   // panic — Wave 20 clears DB + prefs + keys
}
