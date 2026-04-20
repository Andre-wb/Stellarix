package sol.vortexx.android.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import sol.vortexx.android.db.entities.MessageEntity
import sol.vortexx.android.db.entities.MessageFts

@Dao
interface SearchDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun index(row: MessageFts)

    @Query("""
        SELECT m.* FROM messages AS m
        JOIN messages_fts AS fts ON fts.rowid = m.id
        WHERE messages_fts MATCH :query
        ORDER BY m.sentAt DESC
        LIMIT :limit
    """)
    suspend fun search(query: String, limit: Int): List<MessageEntity>

    @Query("DELETE FROM messages_fts WHERE rowid = :id")
    suspend fun unindex(id: Long)
}
