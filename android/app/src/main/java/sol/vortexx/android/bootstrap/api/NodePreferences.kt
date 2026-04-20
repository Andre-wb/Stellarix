package sol.vortexx.android.bootstrap.api

import kotlinx.coroutines.flow.Flow

/**
 * Persistent storage of the user-chosen node URL.
 *
 * Narrow on purpose — JWTs / keys live in a separate encrypted store
 * (Wave 5). Only what we need to boot: the node base URL.
 */
interface NodePreferences {
    val baseUrl: Flow<String?>
    suspend fun setBaseUrl(url: String?)
}
