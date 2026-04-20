package sol.vortexx.android.bootstrap.api

/**
 * Locates reachable Vortex nodes at first launch.
 *
 * Responsibility: turn "the user just opened the app, we have no config"
 * into a working base URL or a clear "can't reach anyone" signal.
 * Nothing else — parsing, storage and UI all live elsewhere.
 */
interface NodeDirectory {
    suspend fun probePrimary(): ProbeResult
    suspend fun probe(url: String): ProbeResult
}

sealed interface ProbeResult {
    data class Ok(val baseUrl: String, val version: String?) : ProbeResult
    data class Unreachable(val tried: String, val reason: String) : ProbeResult
}
