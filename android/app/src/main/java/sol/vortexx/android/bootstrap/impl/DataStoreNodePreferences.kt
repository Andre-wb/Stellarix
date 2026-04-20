package sol.vortexx.android.bootstrap.impl

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import sol.vortexx.android.bootstrap.api.NodePreferences
import javax.inject.Inject
import javax.inject.Singleton

private val Context.store by preferencesDataStore(name = "node_prefs")
private val KEY_BASE_URL = stringPreferencesKey("base_url")

/**
 * [NodePreferences] backed by DataStore-Preferences.
 *
 * DataStore is the recommended replacement for SharedPreferences — it's
 * coroutine-native (Flow) and stable under process death, which matters
 * for the boot flow where the very first write must survive a quick
 * close-and-reopen before the Compose activity has committed.
 */
@Singleton
class DataStoreNodePreferences @Inject constructor(
    @ApplicationContext private val ctx: Context,
) : NodePreferences {

    override val baseUrl: Flow<String?> = ctx.store.data.map { it[KEY_BASE_URL] }

    override suspend fun setBaseUrl(url: String?) {
        ctx.store.edit { prefs ->
            if (url.isNullOrBlank()) prefs.remove(KEY_BASE_URL) else prefs[KEY_BASE_URL] = url
        }
    }
}
