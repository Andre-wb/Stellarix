package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Decrypted message cached locally. `ciphertextHex` is kept alongside the
 * plaintext so we can re-verify or re-export without re-fetching, and so
 * search can fall back to hash-based matching when needed.
 */
@Entity(
    tableName = "messages",
    foreignKeys = [
        ForeignKey(
            entity = RoomEntity::class,
            parentColumns = ["id"],
            childColumns  = ["roomId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("roomId"), Index("sentAt")],
)
data class MessageEntity(
    @PrimaryKey val id: Long,
    val roomId: Long,
    val senderId: Long? = null,           // null when sealed-sender anonymises
    val senderUsername: String? = null,
    val msgType: String = "text",
    val plaintext: String? = null,        // null = not yet decrypted (key pending)
    val ciphertextHex: String,
    val sentAt: Long,                     // epoch millis
    val editedAt: Long? = null,
    val replyTo: Long? = null,
)
