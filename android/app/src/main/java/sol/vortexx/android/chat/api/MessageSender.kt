package sol.vortexx.android.chat.api

/**
 * Send path. Takes plaintext + room, returns a send outcome once the
 * frame has been queued on the WS (not when the server ACKs — delivery
 * receipts are a separate concern).
 */
interface MessageSender {
    suspend fun send(roomId: Long, plaintext: String): SendOutcome
}

sealed interface SendOutcome {
    data class Queued(val localId: Long) : SendOutcome
    data class Error(val reason: String) : SendOutcome
}
