package sol.vortexx.android.search.impl

import sol.vortexx.android.db.dao.SearchDao
import sol.vortexx.android.db.entities.MessageEntity
import sol.vortexx.android.db.entities.MessageFts
import sol.vortexx.android.search.api.SearchRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class Fts4SearchRepository @Inject constructor(
    private val dao: SearchDao,
) : SearchRepository {

    override suspend fun search(query: String, limit: Int): List<MessageEntity> {
        val q = query.trim()
        if (q.isEmpty()) return emptyList()
        val ftsQuery = if (q.endsWith("*") || q.contains(' ')) q else "$q*"
        return runCatching { dao.search(ftsQuery, limit) }.getOrDefault(emptyList())
    }

    override suspend fun index(id: Long, plaintext: String) {
        dao.index(MessageFts(rowid = id, plaintext = plaintext))
    }

    override suspend fun unindex(id: Long) { dao.unindex(id) }
}
