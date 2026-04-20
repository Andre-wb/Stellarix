package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

@Entity(
    tableName = "reactions",
    primaryKeys = ["messageId", "userId", "emoji"],
    foreignKeys = [
        ForeignKey(
            entity = MessageEntity::class,
            parentColumns = ["id"],
            childColumns = ["messageId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("messageId")],
)
data class ReactionEntity(
    val messageId: Long,
    val userId: Long,
    val emoji: String,
    val createdAt: Long,
)
