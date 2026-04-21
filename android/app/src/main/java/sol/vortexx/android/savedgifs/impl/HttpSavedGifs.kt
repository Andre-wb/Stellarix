package sol.vortexx.android.savedgifs.impl

import io.ktor.client.call.body
import io.ktor.client.request.*
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.savedgifs.api.SavedGif
import sol.vortexx.android.savedgifs.api.SavedGifs
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpSavedGifs @Inject constructor(
    private val http: VortexHttpClient,
) : SavedGifs {
    @Serializable private data class Wrap(val gifs: List<SavedGif>)
    @Serializable private data class AddBody(val url: String, val width: Int, val height: Int)

    override suspend fun list(): List<SavedGif> = runCatching {
        val resp = http.client.get("api/saved_gifs")
        if (!resp.status.isSuccess()) return@runCatching emptyList()
        resp.body<Wrap>().gifs
    }.getOrDefault(emptyList())

    override suspend fun add(url: String, width: Int, height: Int): SavedGif? = runCatching {
        val resp = http.client.post("api/saved_gifs") {
            contentType(ContentType.Application.Json)
            setBody(AddBody(url, width, height))
        }
        if (!resp.status.isSuccess()) return@runCatching null
        resp.body<SavedGif>()
    }.getOrNull()

    override suspend fun remove(id: Long) {
        runCatching { http.client.delete("api/saved_gifs/$id") }
    }
}
