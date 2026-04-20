package sol.vortexx.android.settings.impl

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import sol.vortexx.android.db.VortexDatabase
import sol.vortexx.android.settings.api.SettingsStore
import javax.inject.Inject
import javax.inject.Singleton

private val Context.settings by preferencesDataStore(name = "user_settings")
private val KEY_THEME  = stringPreferencesKey("theme")
private val KEY_NOTIFS = booleanPreferencesKey("notifications")

@Singleton
class DataStoreSettingsStore @Inject constructor(
    @ApplicationContext private val ctx: Context,
    private val db: VortexDatabase,
) : SettingsStore {

    override val theme: Flow<String> =
        ctx.settings.data.map { it[KEY_THEME] ?: "system" }

    override val notificationsEnabled: Flow<Boolean> =
        ctx.settings.data.map { it[KEY_NOTIFS] ?: true }

    override suspend fun setTheme(mode: String) {
        ctx.settings.edit { it[KEY_THEME] = mode }
    }

    override suspend fun setNotificationsEnabled(on: Boolean) {
        ctx.settings.edit { it[KEY_NOTIFS] = on }
    }

    override suspend fun wipeAll() {
        // Local panic — nukes DB + user settings. Identity / auth wipe is
        // triggered separately (Settings screen calls both).
        ctx.settings.edit { it.clear() }
        db.clearAllTables()
    }
}
