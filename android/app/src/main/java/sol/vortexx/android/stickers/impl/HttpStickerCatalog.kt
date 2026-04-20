package sol.vortexx.android.stickers.impl

import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.stickers.api.StickerCatalog
import sol.vortexx.android.stickers.api.StickerPack
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpStickerCatalog @Inject constructor(
    private val http: VortexHttpClient,
) : StickerCatalog {

    private val _favorites = MutableStateFlow<List<StickerPack>>(emptyList())
    override fun favoritePacks() = _favorites.asStateFlow()

    init { /* Lazy first-use refresh — full sync lives in a scheduled worker */ }

    override suspend fun addPack(packId: String): Boolean = runCatching {
        val resp = http.client.post("api/stickers/packs/$packId/subscribe")
        if (resp.status.isSuccess()) { refresh(); true } else false
    }.getOrDefault(false)

    override suspend fun removePack(packId: String): Boolean = runCatching {
        val resp = http.client.delete("api/stickers/packs/$packId/subscribe")
        if (resp.status.isSuccess()) { refresh(); true } else false
    }.getOrDefault(false)

    private suspend fun refresh() = runCatching {
        val resp = http.client.get("api/stickers/favorites")
        if (!resp.status.isSuccess()) return@runCatching
        _favorites.value = resp.body<FavoritesResp>().packs.map {
            StickerPack(id = it.id, name = it.name, coverUrl = it.cover_url, stickerCount = it.count)
        }
    }

    @Serializable private data class PackDto(val id: String, val name: String, val cover_url: String, val count: Int)
    @Serializable private data class FavoritesResp(val packs: List<PackDto>)
}
