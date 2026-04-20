package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.RoomEntity

@Dao
interface RoomDao {
    @Query("SELECT * FROM rooms ORDER BY lastMessageAt DESC NULLS LAST, name ASC")
    fun observeAll(): Flow<List<RoomEntity>>

    @Query("SELECT * FROM rooms WHERE id = :id LIMIT 1")
    suspend fun byId(id: Long): RoomEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(room: RoomEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(rooms: List<RoomEntity>)

    @Query("UPDATE rooms SET unreadCount = 0 WHERE id = :id")
    suspend fun markRead(id: Long)

    @Query("DELETE FROM rooms WHERE id = :id")
    suspend fun delete(id: Long)
}
