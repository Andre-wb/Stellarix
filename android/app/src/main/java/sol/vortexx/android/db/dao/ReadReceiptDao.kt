package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.ReadReceiptEntity

@Dao
interface ReadReceiptDao {
    @Query("SELECT * FROM read_receipts WHERE messageId = :id")
    fun forMessage(id: Long): Flow<List<ReadReceiptEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(r: ReadReceiptEntity)

    @Query("SELECT messageId FROM read_receipts WHERE roomId = :roomId AND userId = :userId ORDER BY messageId DESC LIMIT 1")
    suspend fun latestFor(roomId: Long, userId: Long): Long?
}
