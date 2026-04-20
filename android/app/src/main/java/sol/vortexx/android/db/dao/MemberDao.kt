package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.MemberEntity

@Dao
interface MemberDao {
    @Query("SELECT * FROM members WHERE roomId = :roomId ORDER BY username ASC")
    fun observeRoom(roomId: Long): Flow<List<MemberEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(members: List<MemberEntity>)

    @Query("DELETE FROM members WHERE roomId = :roomId AND userId = :userId")
    suspend fun remove(roomId: Long, userId: Long)
}
