package sol.vortexx.android.chat.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.MessageEntity

/**
 * Receive path — server-pushed message events, already decrypted and
 * persisted locally. Screens subscribe to the per-room flow below.
 */
interface IncomingMessages {
    fun messagesIn(roomId: Long): Flow<List<MessageEntity>>
}
