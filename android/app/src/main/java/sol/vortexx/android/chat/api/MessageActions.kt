package sol.vortexx.android.chat.api

/**
 * Wave 13 surface: reactions, edits, replies, threads. Split from
 * [MessageSender] so the chat list UI can be built without depending on
 * action verbs that are wired up later.
 */
interface MessageActions {
    suspend fun react(messageId: Long, emoji: String): Boolean
    suspend fun edit(messageId: Long, newPlaintext: String): Boolean
    suspend fun reply(roomId: Long, replyToMessageId: Long, plaintext: String): SendOutcome
    suspend fun delete(messageId: Long): Boolean
    suspend fun openThread(messageId: Long): Long   // returns the thread's pseudo-roomId
}
