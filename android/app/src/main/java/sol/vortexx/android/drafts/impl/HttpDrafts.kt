package sol.vortexx.android.drafts.impl

import io.ktor.client.call.body
import io.ktor.client.request.*
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.drafts.api.Drafts
import sol.vortexx.android.net.impl.VortexHttpClient
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpDrafts @Inject constructor(
    private val http: VortexHttpClient,
) : Drafts {
    private val cache = ConcurrentHashMap<Long, String>()

    @Serializable private data class Body(val text: String)
    @Serializable private data class Resp(val text: String?)

    override suspend fun get(roomId: Long): String? {
        cache[roomId]?.let { return it.ifEmpty { null } }
        return runCatching {
            val resp = http.client.get("api/rooms/$roomId/draft")
            if (!resp.status.isSuccess()) return@runCatching null
            val t = resp.body<Resp>().text.orEmpty()
            cache[roomId] = t
            t.ifEmpty { null }
        }.getOrNull()
    }

    override suspend fun set(roomId: Long, text: String) {
        cache[roomId] = text
        if (text.isEmpty()) { clear(roomId); return }
        runCatching {
            http.client.put("api/rooms/$roomId/draft") {
                contentType(ContentType.Application.Json)
                setBody(Body(text))
            }
        }
    }

    override suspend fun clear(roomId: Long) {
        cache[roomId] = ""
        runCatching { http.client.delete("api/rooms/$roomId/draft") }
    }
}
