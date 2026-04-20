package sol.vortexx.android.threads.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.ThreadEntity

interface ThreadsRepository {
    fun observeForRoom(roomId: Long): Flow<List<ThreadEntity>>
    suspend fun refresh(roomId: Long): Boolean
    suspend fun create(roomId: Long, parentMessageId: Long, title: String): ThreadEntity?
}
