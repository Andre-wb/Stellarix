package sol.vortexx.android.threads.impl

import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.Serializable
import sol.vortexx.android.db.dao.ThreadDao
import sol.vortexx.android.db.entities.ThreadEntity
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.threads.api.ThreadsRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpThreadsRepository @Inject constructor(
    private val http: VortexHttpClient,
    private val dao: ThreadDao,
) : ThreadsRepository {

    override fun observeForRoom(roomId: Long): Flow<List<ThreadEntity>> =
        dao.observeRoom(roomId)

    override suspend fun refresh(roomId: Long): Boolean = runCatching {
        val resp = http.client.get("api/rooms/$roomId/threads")
        if (!resp.status.isSuccess()) return@runCatching false
        dao.upsertAll(resp.body<List<ThreadDto>>().map(ThreadDto::toEntity))
        true
    }.getOrDefault(false)

    override suspend fun create(roomId: Long, parentMessageId: Long, title: String): ThreadEntity? = runCatching {
        val resp = http.client.post("api/rooms/$roomId/threads") {
            contentType(ContentType.Application.Json)
            setBody(CreateReq(parent_message_id = parentMessageId, title = title))
        }
        if (!resp.status.isSuccess()) return@runCatching null
        val t = resp.body<ThreadDto>().toEntity()
        dao.upsertAll(listOf(t)); t
    }.getOrNull()

    @Serializable private data class CreateReq(val parent_message_id: Long, val title: String)
    @Serializable private data class ThreadDto(
        val id: Long, val room_id: Long, val parent_message_id: Long,
        val title: String, val reply_count: Int = 0, val last_reply_at: Long? = null,
    ) {
        fun toEntity() = ThreadEntity(
            id = id, roomId = room_id, parentMessageId = parent_message_id,
            title = title, replyCount = reply_count, lastReplyAt = last_reply_at,
        )
    }
}
