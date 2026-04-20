package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.ThreadEntity

@Dao
interface ThreadDao {
    @Query("SELECT * FROM threads WHERE roomId = :roomId ORDER BY lastReplyAt DESC NULLS LAST")
    fun observeRoom(roomId: Long): Flow<List<ThreadEntity>>

    @Query("SELECT * FROM threads WHERE id = :id LIMIT 1")
    suspend fun byId(id: Long): ThreadEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(threads: List<ThreadEntity>)
}
