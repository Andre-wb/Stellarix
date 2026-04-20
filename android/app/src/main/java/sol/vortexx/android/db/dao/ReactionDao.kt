package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.ReactionEntity

@Dao
interface ReactionDao {
    @Query("SELECT * FROM reactions WHERE messageId = :id")
    fun forMessage(id: Long): Flow<List<ReactionEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun add(reaction: ReactionEntity)

    @Delete
    suspend fun remove(reaction: ReactionEntity)

    @Query("DELETE FROM reactions WHERE messageId = :id AND userId = :uid AND emoji = :emoji")
    suspend fun removeBy(id: Long, uid: Long, emoji: String)
}
