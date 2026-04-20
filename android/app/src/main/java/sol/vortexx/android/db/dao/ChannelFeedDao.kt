package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.ChannelFeedEntity

@Dao
interface ChannelFeedDao {
    @Query("SELECT * FROM channel_feeds WHERE roomId = :roomId")
    fun observeRoom(roomId: Long): Flow<List<ChannelFeedEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(feed: ChannelFeedEntity)

    @Query("DELETE FROM channel_feeds WHERE id = :id")
    suspend fun delete(id: Long)
}
