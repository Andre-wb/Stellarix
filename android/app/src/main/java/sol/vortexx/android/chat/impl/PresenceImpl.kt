package sol.vortexx.android.chat.impl

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import sol.vortexx.android.chat.api.Presence
import sol.vortexx.android.db.dao.ReadReceiptDao
import sol.vortexx.android.db.entities.ReadReceiptEntity
import sol.vortexx.android.ws.api.WsClient
import sol.vortexx.android.ws.api.WsFrame
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Typing is kept in-memory (per-process, 3s TTL). Read receipts persist
 * via [ReadReceiptDao] so "seen" badges survive process death.
 */
@Singleton
class PresenceImpl @Inject constructor(
    private val ws: WsClient,
    private val receipts: ReadReceiptDao,
) : Presence {

    private val typing = MutableStateFlow<Map<Long, Map<String, Long>>>(emptyMap())
    private val reads  = MutableStateFlow<Map<Long, Map<Long, Long>>>(emptyMap())
    private val scope  = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val json   = Json { ignoreUnknownKeys = true }

    init { scope.launch { observe() } }

    override fun typingIn(roomId: Long): Flow<Set<String>> =
        typing.map { m -> m[roomId]?.keys.orEmpty() }

    override fun readUpTo(roomId: Long): Flow<Map<Long, Long>> =
        reads.map { it[roomId].orEmpty() }

    override suspend fun sendTyping(roomId: Long) {
        ws.send(WsFrame(json.encodeToString(
            Frame.serializer(),
            Frame(type = "typing", room_id = roomId),
        )))
    }

    override suspend fun markRead(roomId: Long, messageId: Long) {
        receipts.upsert(ReadReceiptEntity(
            roomId = roomId, userId = 0, messageId = messageId,
            readAt = System.currentTimeMillis(),
        ))
        ws.send(WsFrame(json.encodeToString(
            Frame.serializer(),
            Frame(type = "read", room_id = roomId, message_id = messageId),
        )))
    }

    // ── WS observer ────────────────────────────────────────────────────

    private suspend fun observe() {
        ws.incoming.collect { frame ->
            val obj = runCatching { json.parseToJsonElement(frame.text).jsonObject }.getOrNull()
                ?: return@collect
            when (obj["type"]?.jsonPrimitive?.content) {
                "typing" -> {
                    val roomId = obj["room_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return@collect
                    val who    = obj["username"]?.jsonPrimitive?.content ?: return@collect
                    typing.update { m ->
                        val inner = m[roomId].orEmpty().toMutableMap()
                        inner[who] = System.currentTimeMillis()
                        m + (roomId to inner)
                    }
                    scope.launch { prune(roomId, who) }
                }
                "read" -> {
                    val roomId = obj["room_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return@collect
                    val userId = obj["user_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return@collect
                    val msgId  = obj["message_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return@collect
                    reads.update { m ->
                        val inner = m[roomId].orEmpty().toMutableMap()
                        inner[userId] = msgId
                        m + (roomId to inner)
                    }
                }
                else -> { /* not ours */ }
            }
        }
    }

    private suspend fun prune(roomId: Long, who: String) {
        delay(3_000)
        typing.update { m ->
            val inner = m[roomId]?.toMutableMap() ?: return@update m
            if (System.currentTimeMillis() - (inner[who] ?: 0) >= 3_000) inner.remove(who)
            if (inner.isEmpty()) m - roomId else m + (roomId to inner)
        }
    }

    @Serializable
    private data class Frame(
        val type: String,
        val room_id: Long? = null,
        val message_id: Long? = null,
    )
}

private inline fun <T> MutableStateFlow<T>.update(block: (T) -> T) {
    while (true) {
        val prev = value
        val next = block(prev)
        if (compareAndSet(prev, next)) return
    }
}
