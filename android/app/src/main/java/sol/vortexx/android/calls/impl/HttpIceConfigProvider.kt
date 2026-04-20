package sol.vortexx.android.calls.impl

import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.calls.api.IceConfigProvider
import sol.vortexx.android.calls.api.IceServer
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpIceConfigProvider @Inject constructor(
    private val http: VortexHttpClient,
) : IceConfigProvider {

    override suspend fun current(): List<IceServer> = runCatching {
        val resp = http.client.get("v1/calls/ice")
        if (!resp.status.isSuccess()) return@runCatching DEFAULT_ICE
        resp.body<IceResp>().servers.map {
            IceServer(urls = it.urls, username = it.username, credential = it.credential)
        }
    }.getOrDefault(DEFAULT_ICE)

    @Serializable private data class IceDto(
        val urls: List<String>,
        val username: String? = null,
        val credential: String? = null,
    )
    @Serializable private data class IceResp(val servers: List<IceDto>)

    private companion object {
        // Fallback when the node doesn't surface TURN creds (e.g. fresh
        // install). Google's public STUN works for unblocked LANs.
        val DEFAULT_ICE = listOf(IceServer(urls = listOf("stun:stun.l.google.com:19302")))
    }
}
