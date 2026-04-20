package sol.vortexx.android.calls.api

/**
 * STUN / TURN servers fetched from the node's `/v1/calls/ice`.
 * The list changes when the operator rotates TURN creds, so the call
 * controller refreshes on every new call instead of caching forever.
 */
interface IceConfigProvider {
    suspend fun current(): List<IceServer>
}

data class IceServer(
    val urls: List<String>,
    val username: String? = null,
    val credential: String? = null,
)
