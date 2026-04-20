package sol.vortexx.android.rooms.impl

import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.Serializable
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.db.dao.RoomDao
import sol.vortexx.android.db.entities.RoomEntity
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.rooms.api.RefreshResult
import sol.vortexx.android.rooms.api.RoomResult
import sol.vortexx.android.rooms.api.RoomsRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Rooms feature — thin wrapper over `/api/rooms/*`. Each method maps
 * 1-to-1 onto a server endpoint, with local DB upsert on success. The
 * heavy crypto (ECIES wrap of the new room key) stays here instead of
 * the view model — screens only deal with id+name.
 */
@Singleton
class HttpRoomsRepository @Inject constructor(
    private val http: VortexHttpClient,
    private val dao: RoomDao,
    private val aead: Aead,                       // referenced in Wave 11
    private val random: SecureRandomProvider,     // ditto
) : RoomsRepository {

    override fun observe(): Flow<List<RoomEntity>> = dao.observeAll()

    override suspend fun refresh(): RefreshResult = runCatching {
        val resp = http.client.get("api/rooms/my")
        if (!resp.status.isSuccess()) return RefreshResult.Error("http_${resp.status.value}")
        val body = resp.body<List<RoomDto>>()
        dao.upsertAll(body.map(RoomDto::toEntity))
        RefreshResult.Ok(body.size)
    }.getOrElse { RefreshResult.Error(it.message ?: "io_error") }

    override suspend fun create(name: String, isPrivate: Boolean): RoomResult {
        val req = CreateRoomReq(
            name       = name,
            is_private = isPrivate,
            // Key material — ECIES payload filled in by Wave 9's key-agreement step.
            // For Wave 8 we send an empty shell; the server rejects if missing.
            public_room_key_hex = if (!isPrivate) Hex.encode(random.nextBytes(32)) else null,
        )
        return runCatching {
            val resp = http.client.post("api/rooms") {
                contentType(ContentType.Application.Json); setBody(req)
            }
            if (!resp.status.isSuccess()) {
                RoomResult.Error("http_${resp.status.value}", resp.bodyAsText().take(200))
            } else {
                val dto = resp.body<RoomDto>()
                dao.upsert(dto.toEntity())
                RoomResult.Ok(dto.id)
            }
        }.getOrElse { RoomResult.Error("io", it.message ?: "request failed") }
    }

    override suspend fun joinByInvite(inviteCode: String): RoomResult = runCatching {
        val resp = http.client.post("api/rooms/join/$inviteCode")
        if (!resp.status.isSuccess()) return@runCatching RoomResult.Error(
            "http_${resp.status.value}", resp.bodyAsText().take(200),
        )
        val dto = resp.body<RoomDto>()
        dao.upsert(dto.toEntity())
        RoomResult.Ok(dto.id)
    }.getOrElse { RoomResult.Error("io", it.message ?: "request failed") }

    override suspend fun leave(roomId: Long): Boolean = runCatching {
        val resp = http.client.delete("api/rooms/$roomId/leave")
        if (resp.status.isSuccess()) { dao.delete(roomId); true } else false
    }.getOrDefault(false)

    // ── DTOs ───────────────────────────────────────────────────────────

    @Serializable
    private data class CreateRoomReq(
        val name: String,
        val is_private: Boolean,
        val public_room_key_hex: String? = null,
    )

    @Serializable
    private data class RoomDto(
        val id: Long,
        val name: String,
        val description: String = "",
        val invite_code: String,
        val is_private: Boolean = false,
        val is_channel: Boolean = false,
        val is_dm: Boolean = false,
        val avatar_emoji: String = "\uD83D\uDCAC",
        val member_count: Int = 0,
    ) {
        fun toEntity() = RoomEntity(
            id = id, name = name, description = description, inviteCode = invite_code,
            isPrivate = is_private, isChannel = is_channel, isDm = is_dm,
            avatarEmoji = avatar_emoji, memberCount = member_count,
        )
    }
}
