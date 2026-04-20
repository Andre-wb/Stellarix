package sol.vortexx.android.chat.impl

import io.ktor.client.request.delete
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.chat.api.MessageActions
import sol.vortexx.android.chat.api.MessageSender
import sol.vortexx.android.chat.api.SendOutcome
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.db.dao.MessageDao
import sol.vortexx.android.db.dao.ReactionDao
import sol.vortexx.android.db.entities.ReactionEntity
import sol.vortexx.android.keys.api.KeyAcquisition
import sol.vortexx.android.keys.api.RoomKeyProvider
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Server-driven message actions. Each method mirrors a `/api/messages/*`
 * endpoint on the node. Local DB updates are optimistic — the server's
 * WS broadcast (`message_updated`, `reaction_added`, …) reconciles the
 * final state in [ChatEngine].
 */
@Singleton
class MessageActionsImpl @Inject constructor(
    private val http: VortexHttpClient,
    private val aead: Aead,
    private val keys: RoomKeyProvider,
    private val messages: MessageDao,
    private val reactions: ReactionDao,
    private val sender: MessageSender,
) : MessageActions {

    override suspend fun react(messageId: Long, emoji: String): Boolean = runCatching {
        // Optimistic — we don't yet know the current user id locally, so
        // the DAO row uses 0 as a placeholder. The WS echo will overwrite.
        reactions.add(ReactionEntity(
            messageId = messageId, userId = 0, emoji = emoji,
            createdAt = System.currentTimeMillis(),
        ))
        val resp = http.client.post("api/messages/$messageId/react") {
            contentType(ContentType.Application.Json); setBody(ReactReq(emoji))
        }
        resp.status.isSuccess()
    }.getOrDefault(false)

    override suspend fun edit(messageId: Long, newPlaintext: String): Boolean {
        val existing = messages.byId(messageId) ?: return false
        val keyAcq = keys.keyFor(existing.roomId)
        if (keyAcq !is KeyAcquisition.Ready) return false
        val newCt = Hex.encode(aead.encrypt(Hex.decode(keyAcq.keyHex), newPlaintext.toByteArray()))

        messages.upsert(existing.copy(
            plaintext = newPlaintext, ciphertextHex = newCt,
            editedAt = System.currentTimeMillis(),
        ))
        return runCatching {
            http.client.put("api/messages/$messageId") {
                contentType(ContentType.Application.Json)
                setBody(EditReq(newCt))
            }.status.isSuccess()
        }.getOrDefault(false)
    }

    override suspend fun reply(roomId: Long, replyToMessageId: Long, plaintext: String): SendOutcome {
        // Server-side reply is just a normal send with reply_to field; for
        // the client, we queue via MessageSender and tag the local row.
        val outcome = sender.send(roomId, plaintext)
        if (outcome is SendOutcome.Queued) {
            messages.lastN(roomId, 1).firstOrNull()?.let {
                messages.upsert(it.copy(replyTo = replyToMessageId))
            }
        }
        return outcome
    }

    override suspend fun delete(messageId: Long): Boolean = runCatching {
        messages.delete(messageId)
        http.client.delete("api/messages/$messageId").status.isSuccess()
    }.getOrDefault(false)

    override suspend fun openThread(messageId: Long): Long {
        // Thread id = deterministic mapping over messageId so the UI
        // router can open "thread:MSG" without an extra round-trip. Server
        // creates the virtual room on first send.
        return -messageId   // negative id convention distinguishes from real rooms
    }

    @Serializable private data class ReactReq(val emoji: String)
    @Serializable private data class EditReq(val ciphertext: String)
}
