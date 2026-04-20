package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Forum / discussion thread — spawned from a parent message or a
 * channel post. Stored separately from rooms so a thread list can
 * appear inline under a post without entering a sub-room.
 */
@Entity(
    tableName = "threads",
    foreignKeys = [
        ForeignKey(
            entity = MessageEntity::class,
            parentColumns = ["id"],
            childColumns = ["parentMessageId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("parentMessageId"), Index("roomId")],
)
data class ThreadEntity(
    @PrimaryKey val id: Long,
    val roomId: Long,
    val parentMessageId: Long,
    val title: String,
    val replyCount: Int = 0,
    val lastReplyAt: Long? = null,
)
