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
import sol.vortexx.android.ws.api.WsClient
import sol.vortexx.android.ws.api.WsFrame
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.random.Random

/**
 * End-to-end chat engine.
 *
 * Separated from the UI/VM on purpose — the ViewModel imports [MessageSender]
 * and [IncomingMessages] only; the AEAD + key flow stay here so mixing the
 * encryption path with Compose state is impossible.
 */
@Singleton
class ChatEngine @Inject constructor(
    private val ws: WsClient,
    private val aead: Aead,
    private val keys: RoomKeyProvider,
    private val dao: MessageDao,
) : MessageSender, IncomingMessages {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val json  = Json { ignoreUnknownKeys = true }

    init { scope.launch { observeIncoming() } }

    override fun messagesIn(roomId: Long): Flow<List<MessageEntity>> = dao.observeRoom(roomId)

    override suspend fun send(roomId: Long, plaintext: String): SendOutcome {
        val key = when (val r = keys.keyFor(roomId)) {
            is KeyAcquisition.Ready -> r.keyHex
            is KeyAcquisition.Pending -> return SendOutcome.Error("key_pending:${r.reason}")
            is KeyAcquisition.Error  -> return SendOutcome.Error(r.reason)
        }
        val packed = aead.encrypt(Hex.decode(key), plaintext.toByteArray(Charsets.UTF_8))
        val ctHex = Hex.encode(packed)

        val localId = Random.nextLong(Long.MAX_VALUE - 1) + 1
        dao.upsert(MessageEntity(
            id = localId, roomId = roomId, plaintext = plaintext,
            ciphertextHex = ctHex, sentAt = System.currentTimeMillis(),
        ))
        ws.send(WsFrame(json.encodeToString(
            OutFrame.serializer(),
            OutFrame(action = "send_message", room_id = roomId, ciphertext = ctHex),
        )))
        return SendOutcome.Queued(localId)
    }

    /** WS receive — decrypt + persist. Silent drop on bad frames: the
     *  WS layer already logged and the room will self-heal on refresh. */
    private suspend fun observeIncoming() {
        ws.incoming.collect { frame ->
            val obj = runCatching { json.parseToJsonElement(frame.text).jsonObject }.getOrNull()
                ?: return@collect
            if (obj["type"]?.jsonPrimitive?.content != "peer_message") return@collect

            val roomId = obj["room_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: return@collect
            val ctHex  = obj["ciphertext"]?.jsonPrimitive?.content ?: return@collect
            val sender = obj["sender"]?.jsonPrimitive?.content

            val keyAcq = keys.keyFor(roomId)
            if (keyAcq !is KeyAcquisition.Ready) {
                // No key yet — store ciphertext so the view can re-try later.
                dao.upsert(MessageEntity(
                    id = System.nanoTime(),
                    roomId = roomId, senderUsername = sender,
                    plaintext = null, ciphertextHex = ctHex,
                    sentAt = System.currentTimeMillis(),
                ))
                return@collect
            }
            val plaintext = runCatching {
                String(aead.decrypt(Hex.decode(keyAcq.keyHex), Hex.decode(ctHex)), Charsets.UTF_8)
            }.getOrNull()

            dao.upsert(MessageEntity(
                id = System.nanoTime(),
                roomId = roomId, senderUsername = sender,
                plaintext = plaintext, ciphertextHex = ctHex,
                sentAt = System.currentTimeMillis(),
            ))
        }
    }

    @Serializable
    private data class OutFrame(val action: String, val room_id: Long, val ciphertext: String)
}
