package sol.vortexx.android.federation.impl

import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import sol.vortexx.android.federation.api.Mirror
import sol.vortexx.android.federation.api.MirrorDirectory
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpMirrorDirectory @Inject constructor(
    private val http: VortexHttpClient,
) : MirrorDirectory {

    private val _mirrors = MutableStateFlow<List<Mirror>>(emptyList())
    override val mirrors = _mirrors.asStateFlow()

    override suspend fun refresh(): Boolean = runCatching {
        val resp = http.client.get("v1/mirrors")
        if (!resp.status.isSuccess()) return@runCatching false
        val body = resp.body<MirrorListResp>()
        _mirrors.value = body.mirrors.map {
            Mirror(
                id = it.id, url = it.url, kind = it.kind,
                lastSeenEpoch = it.last_seen, healthy = it.healthy,
            )
        }
        true
    }.getOrDefault(false)

    override suspend fun probe(mirrorId: String): Boolean = runCatching {
        val m = _mirrors.value.firstOrNull { it.id == mirrorId } ?: return false
        val resp = http.client.get("${m.url}/v1/health")
        resp.status.isSuccess()
    }.getOrDefault(false)

    @Serializable private data class MirrorDto(
        val id: String, val url: String, val kind: String,
        val last_seen: Long?, val healthy: Boolean,
    )
    @Serializable private data class MirrorListResp(val mirrors: List<MirrorDto>)
}
