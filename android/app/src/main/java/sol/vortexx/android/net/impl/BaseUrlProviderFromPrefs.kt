package sol.vortexx.android.net.impl

import kotlinx.coroutines.flow.first
import sol.vortexx.android.bootstrap.api.NodePreferences
import sol.vortexx.android.net.api.BaseUrlProvider
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Reads the user-chosen base URL from the bootstrap feature's DataStore.
 * The `first()` call returns the cached value without suspending when
 * DataStore has already emitted it — which is the common case once the
 * Bootstrap screen has handed control off.
 */
@Singleton
class BaseUrlProviderFromPrefs @Inject constructor(
    private val prefs: NodePreferences,
) : BaseUrlProvider {
    override suspend fun current(): String? = prefs.baseUrl.first()
}
