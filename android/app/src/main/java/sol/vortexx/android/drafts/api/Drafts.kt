package sol.vortexx.android.drafts.api

interface Drafts {
    suspend fun get(roomId: Long): String?
    suspend fun set(roomId: Long, text: String)
    suspend fun clear(roomId: Long)
}
