package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.SpaceEntity

@Dao
interface SpaceDao {
    @Query("SELECT * FROM spaces ORDER BY name ASC")
    fun observeAll(): Flow<List<SpaceEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(spaces: List<SpaceEntity>)

    @Query("DELETE FROM spaces WHERE id = :id")
    suspend fun delete(id: Long)
}
