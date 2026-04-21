package sol.vortexx.android.scheduled.api

import kotlinx.serialization.Serializable

@Serializable
data class ScheduledMessage(
    val id: Long,
    val room_id: Long,
    val ciphertext_b64: String,
    val send_at: Long,
    val created_at: Long,
)

interface ScheduledMessages {
    suspend fun list(roomId: Long): List<ScheduledMessage>
    suspend fun schedule(roomId: Long, ciphertextB64: String, sendAt: Long): ScheduledMessage?
    suspend fun cancel(id: Long)
    suspend fun edit(id: Long, newCiphertextB64: String, newSendAt: Long?): ScheduledMessage?
}
