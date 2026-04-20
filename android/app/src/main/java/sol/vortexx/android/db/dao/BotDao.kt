package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.BotEntity

@Dao
interface BotDao {
    @Query("SELECT * FROM bots ORDER BY installCount DESC")
    fun observeMarketplace(): Flow<List<BotEntity>>

    @Query("SELECT * FROM bots WHERE installed = 1 ORDER BY name ASC")
    fun observeInstalled(): Flow<List<BotEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(bots: List<BotEntity>)

    @Query("UPDATE bots SET installed = :installed WHERE id = :id")
    suspend fun setInstalled(id: Long, installed: Boolean)
}
