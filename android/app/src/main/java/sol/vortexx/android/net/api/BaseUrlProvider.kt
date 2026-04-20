package sol.vortexx.android.net.api

/**
 * Source of the node base URL the network layer points at.
 *
 * Split from [sol.vortexx.android.bootstrap.api.NodePreferences] because
 * the net layer shouldn't be able to *mutate* the base URL — only read
 * the current one. The bootstrap feature owns the write path.
 */
interface BaseUrlProvider {
    /** Returns the saved base URL, or null if bootstrap hasn't completed. */
    suspend fun current(): String?
}
