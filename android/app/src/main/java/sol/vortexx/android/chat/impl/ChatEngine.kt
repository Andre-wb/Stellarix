package sol.vortexx.android.chat.impl

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import sol.vortexx.android.chat.api.IncomingMessages
import sol.vortexx.android.chat.api.MessageSender
import sol.vortexx.android.chat.api.SendOutcome
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.db.dao.MessageDao
import sol.vortexx.android.db.entities.MessageEntity
import sol.vortexx.android.keys.api.KeyAcquisition
import sol.vortexx.android.keys.api.RoomKeyProvider
import sol.vortexx.android.search.api.SearchRepository
import sol.vortexx.android.ws.api.WsClient
import sol.vortexx.android.ws.api.WsFrame
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.random.Random

/**
 * End-to-end chat engine. Owns three responsibilities:
 *   1. Outbound encrypt + persist + WS send
 *   2. Inbound WS receive → decrypt → persist
 *   3. On key-arrival events, re-decrypt any messages that previously
 *      landed while the room key was still Pending.
 *
 * Every plaintext that lands here is also pushed into [SearchRepository]
 * so full-text search covers every delivered message.
 */
@Singleton
class ChatEngine @Inject constructor(
    private val ws: WsClient,
    private val aead: Aead,
    private val keys: RoomKeyProvider,
    private val dao: MessageDao,
    private val search: SearchRepository,
) : MessageSender, IncomingMessages {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val json  = Json { ignoreUnknownKeys = true }

    init { scope.launch { observeIncoming() } }

    override fun messagesIn(roomId: Long): Flow<List<MessageEntity>> = dao.observeRoom(roomId)

    override suspend fun send(roomId: Long, plaintext: String): SendOutcome {
        val key = when (val r = keys.keyFor(roomId)) {
            is KeyAcquisition.Ready   -> r.keyHex
            is KeyAcquisition.Pending -> return SendOutcome.Error("key_pending:${r.reason}")
            is KeyAcquisition.Error   -> return SendOutcome.Error(r.reason)
        }
        val packed = aead.encrypt(Hex.decode(key), plaintext.toByteArray(Charsets.UTF_8))
        val ctHex  = Hex.encode(packed)

        val localId = Random.nextLong(Long.MAX_VALUE - 1) + 1
        val msg = MessageEntity(
            id = localId, roomId = roomId, plaintext = plaintext,
            ciphertextHex = ctHex, sentAt = System.currentTimeMillis(),
        )
        dao.upsert(msg)
        search.index(msg.id, plaintext)
        ws.send(WsFrame(json.encodeToString(
            OutFrame.serializer(),
            OutFrame(action = "send_message", room_id = roomId, ciphertext = ctHex),
        )))
        return SendOutcome.Queued(localId)
    }

    /**
     * WS receive loop.
     *   - `peer_message` → decrypt + store + index
     *   - `public_room_key_updated` / `room_key` → re-decrypt any backlog
     *     that was stored with plaintext=null because the key wasn't ready.
     */
    private suspend fun observeIncoming() {
        ws.incoming.collect { frame ->
            val obj = runCatching { json.parseToJsonElement(frame.text).jsonObject }.getOrNull()
                ?: return@collect
            when (obj["type"]?.jsonPrimitive?.content) {
                "peer_message" -> onPeerMessage(obj)
                "public_room_key_updated", "room_key", "room_key_rotated" -> {
                    val roomId = obj["room_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return@collect
                    retryUndecrypted(roomId)
                }
                else -> { /* not ours */ }
            }
        }
    }

    private suspend fun onPeerMessage(obj: kotlinx.serialization.json.JsonObject) {
        val roomId = obj["room_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return
        val ctHex  = obj["ciphertext"]?.jsonPrimitive?.content ?: return
        val sender = obj["sender"]?.jsonPrimitive?.content
        val id     = obj["msg_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: System.nanoTime()

        val plaintext = tryDecrypt(roomId, ctHex)
        val msg = MessageEntity(
            id = id, roomId = roomId, senderUsername = sender,
            plaintext = plaintext, ciphertextHex = ctHex,
            sentAt = System.currentTimeMillis(),
        )
        dao.upsert(msg)
        if (plaintext != null) search.index(id, plaintext)
    }

    /**
     * Walk the backlog of not-yet-decrypted messages in [roomId] and try
     * to decrypt them now that a fresh key has arrived. Idempotent —
     * already-decrypted rows are left alone by [MessageDao.undecrypted].
     */
    private suspend fun retryUndecrypted(roomId: Long) {
        val pending = dao.undecrypted(roomId)
        if (pending.isEmpty()) return
        for (row in pending) {
            val plaintext = tryDecrypt(roomId, row.ciphertextHex) ?: continue
            dao.upsert(row.copy(plaintext = plaintext))
            search.index(row.id, plaintext)
        }
    }

    private suspend fun tryDecrypt(roomId: Long, ctHex: String): String? {
        val keyAcq = keys.keyFor(roomId)
        if (keyAcq !is KeyAcquisition.Ready) return null
        return runCatching {
            String(aead.decrypt(Hex.decode(keyAcq.keyHex), Hex.decode(ctHex)), Charsets.UTF_8)
        }.getOrNull()
    }

    @Serializable
    private data class OutFrame(val action: String, val room_id: Long, val ciphertext: String)
}
