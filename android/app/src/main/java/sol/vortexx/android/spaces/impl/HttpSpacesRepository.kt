package sol.vortexx.android.spaces.impl

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
import sol.vortexx.android.db.dao.SpaceDao
import sol.vortexx.android.db.entities.SpaceEntity
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.spaces.api.SpacesRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpSpacesRepository @Inject constructor(
    private val http: VortexHttpClient,
    private val dao: SpaceDao,
) : SpacesRepository {

    override fun observe(): Flow<List<SpaceEntity>> = dao.observeAll()

    override suspend fun refresh(): Boolean = runCatching {
        val resp = http.client.get("api/spaces/my")
        if (!resp.status.isSuccess()) return@runCatching false
        val body = resp.body<List<SpaceDto>>()
        dao.upsertAll(body.map(SpaceDto::toEntity))
        true
    }.getOrDefault(false)

    override suspend fun create(name: String, isPublic: Boolean): SpaceEntity? = runCatching {
        val resp = http.client.post("api/spaces") {
            contentType(ContentType.Application.Json)
            setBody(CreateReq(name, isPublic))
        }
        if (!resp.status.isSuccess()) return@runCatching null
        val s = resp.body<SpaceDto>().toEntity()
        dao.upsertAll(listOf(s)); s
    }.getOrNull()

    override suspend fun leave(id: Long): Boolean = runCatching {
        val resp = http.client.delete("api/spaces/$id/leave")
        if (resp.status.isSuccess()) { dao.delete(id); true } else false
    }.getOrDefault(false)

    @Serializable private data class CreateReq(val name: String, val is_public: Boolean)
    @Serializable private data class SpaceDto(
        val id: Long, val name: String,
        val creator_id: Long, val avatar_emoji: String = "\uD83C\uDF0C",
        val member_count: Int = 0, val is_public: Boolean = false,
    ) {
        fun toEntity() = SpaceEntity(
            id = id, name = name, ownerId = creator_id,
            avatarEmoji = avatar_emoji, memberCount = member_count, isPublic = is_public,
        )
    }
}
