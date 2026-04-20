package sol.vortexx.android.feeds.impl

import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.Serializable
import sol.vortexx.android.db.dao.ChannelFeedDao
import sol.vortexx.android.db.entities.ChannelFeedEntity
import sol.vortexx.android.feeds.api.ChannelFeedRepository
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpChannelFeedRepository @Inject constructor(
    private val http: VortexHttpClient,
    private val dao: ChannelFeedDao,
) : ChannelFeedRepository {

    override fun observe(roomId: Long): Flow<List<ChannelFeedEntity>> = dao.observeRoom(roomId)

    override suspend fun refresh(roomId: Long): Boolean = runCatching {
        val resp = http.client.get("api/rooms/$roomId/feeds")
        if (!resp.status.isSuccess()) return@runCatching false
        resp.body<List<FeedDto>>().forEach { dto ->
            dao.upsert(ChannelFeedEntity(
                id = dto.id, roomId = dto.room_id,
                feedType = dto.feed_type, url = dto.url,
                lastFetched = dto.last_fetched, isActive = dto.is_active,
            ))
        }
        true
    }.getOrDefault(false)

    override suspend fun subscribe(roomId: Long, url: String, feedType: String): Boolean = runCatching {
        val resp = http.client.post("api/rooms/$roomId/feeds") {
            contentType(ContentType.Application.Json)
            setBody(SubReq(url = url, feed_type = feedType))
        }
        if (!resp.status.isSuccess()) return@runCatching false
        val dto = resp.body<FeedDto>()
        dao.upsert(ChannelFeedEntity(
            id = dto.id, roomId = dto.room_id,
            feedType = dto.feed_type, url = dto.url,
            lastFetched = dto.last_fetched, isActive = dto.is_active,
        ))
        true
    }.getOrDefault(false)

    override suspend fun unsubscribe(feedId: Long): Boolean = runCatching {
        val resp = http.client.delete("api/feeds/$feedId")
        if (resp.status.isSuccess()) { dao.delete(feedId); true } else false
    }.getOrDefault(false)

    @Serializable private data class SubReq(val url: String, val feed_type: String)
    @Serializable private data class FeedDto(
        val id: Long, val room_id: Long, val feed_type: String, val url: String,
        val last_fetched: Long? = null, val is_active: Boolean = true,
    )
}
