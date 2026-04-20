package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import sol.vortexx.android.db.entities.RoomKeyEntity

@Dao
interface RoomKeyDao {
    @Query("SELECT * FROM room_keys WHERE roomId = :roomId LIMIT 1")
    suspend fun forRoom(roomId: Long): RoomKeyEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(key: RoomKeyEntity)

    @Query("DELETE FROM room_keys WHERE roomId = :roomId")
    suspend fun delete(roomId: Long)
}
