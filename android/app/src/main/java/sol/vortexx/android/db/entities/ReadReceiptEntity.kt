package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.Index

/**
 * Per-user read position in a room. Written when the chat screen scrolls
 * past a message; shown as "seen by N" under outgoing bubbles.
 */
@Entity(
    tableName = "read_receipts",
    primaryKeys = ["roomId", "userId"],
    indices = [Index("messageId")],
)
data class ReadReceiptEntity(
    val roomId: Long,
    val userId: Long,
    val messageId: Long,
    val readAt: Long,
)
