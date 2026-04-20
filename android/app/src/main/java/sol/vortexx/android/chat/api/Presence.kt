package sol.vortexx.android.chat.api

import kotlinx.coroutines.flow.Flow

/**
 * Transient live-state for a room:
 *   - who's typing right now (auto-expires after 3s)
 *   - who has read which message (read-through line)
 *
 * Separated from [MessageSender] because these events don't persist in
 * the message log — they're WS pings that flip a short-lived UI bit.
 */
interface Presence {
    fun typingIn(roomId: Long): Flow<Set<String>>
    fun readUpTo(roomId: Long): Flow<Map<Long /*userId*/, Long /*messageId*/>>

    suspend fun sendTyping(roomId: Long)
    suspend fun markRead(roomId: Long, messageId: Long)
}
