package sol.vortexx.android.federation.api

import kotlinx.coroutines.flow.Flow

/**
 * Wave 19 — mirror list probing and federated-room join.
 *
 * When the primary node is unreachable the app falls back through the
 * known mirrors (pulled from `/v1/mirrors` last time we had a session)
 * and, if that fails too, offers multihop-join to any peer reachable
 * from any mirror.
 */
interface MirrorDirectory {
    val mirrors: Flow<List<Mirror>>
    suspend fun refresh(): Boolean
    suspend fun probe(mirrorId: String): Boolean
}

data class Mirror(
    val id: String,
    val url: String,
    val kind: String,          // "tunnel" | "tor" | "ipfs" | "direct"
    val lastSeenEpoch: Long?,
    val healthy: Boolean,
)
