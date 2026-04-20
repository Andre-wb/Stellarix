package sol.vortexx.android.search.api

import sol.vortexx.android.db.entities.MessageEntity

interface SearchRepository {
    /**
     * Local full-text search over decrypted messages cached on this device.
     * FTS4 syntax: prefix match with `*`, boolean AND/OR, `"quoted phrase"`.
     */
    suspend fun search(query: String, limit: Int = 50): List<MessageEntity>

    /** Index a newly decrypted message. Called from ChatEngine. */
    suspend fun index(id: Long, plaintext: String)

    /** Remove from the index (on delete). */
    suspend fun unindex(id: Long)
}
