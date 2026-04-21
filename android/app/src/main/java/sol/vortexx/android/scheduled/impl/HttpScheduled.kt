package sol.vortexx.android.scheduled.impl

import io.ktor.client.call.body
import io.ktor.client.request.*
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.scheduled.api.ScheduledMessage
import sol.vortexx.android.scheduled.api.ScheduledMessages
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpScheduled @Inject constructor(
    private val http: VortexHttpClient,
) : ScheduledMessages {
    @Serializable private data class Wrap(val items: List<ScheduledMessage>)
    @Serializable private data class AddBody(val room_id: Long, val ciphertext_b64: String, val send_at: Long)
    @Serializable private data class EditBody(val ciphertext_b64: String, val send_at: Long? = null)

    override suspend fun list(roomId: Long): List<ScheduledMessage> = runCatching {
        val resp = http.client.get("api/scheduled") { url { parameters.append("room_id", roomId.toString()) } }
        if (!resp.status.isSuccess()) emptyList() else resp.body<Wrap>().items
    }.getOrDefault(emptyList())

    override suspend fun schedule(roomId: Long, ciphertextB64: String, sendAt: Long): ScheduledMessage? = runCatching {
        val resp = http.client.post("api/scheduled") {
            contentType(ContentType.Application.Json)
            setBody(AddBody(roomId, ciphertextB64, sendAt))
        }
        if (!resp.status.isSuccess()) null else resp.body<ScheduledMessage>()
    }.getOrNull()

    override suspend fun cancel(id: Long) {
        runCatching { http.client.delete("api/scheduled/$id") }
    }

    override suspend fun edit(id: Long, newCiphertextB64: String, newSendAt: Long?): ScheduledMessage? = runCatching {
        val resp = http.client.patch("api/scheduled/$id") {
            contentType(ContentType.Application.Json)
            setBody(EditBody(newCiphertextB64, newSendAt))
        }
        if (!resp.status.isSuccess()) null else resp.body<ScheduledMessage>()
    }.getOrNull()
}
