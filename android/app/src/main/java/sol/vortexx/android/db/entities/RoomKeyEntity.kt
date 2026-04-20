package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.PrimaryKey

/**
 * Cached symmetric room key. Populated by:
 *   - ECIES flow (private rooms)
 *   - Variant-B fast path (public rooms), via GET /api/rooms/{id}/public-key
 *
 * `source` lets us warn the user if a public→private flip happens and the
 * cached public-derived key is now considered stale.
 */
@Entity(
    tableName = "room_keys",
    foreignKeys = [
        ForeignKey(
            entity = RoomEntity::class,
            parentColumns = ["id"],
            childColumns  = ["roomId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
)
data class RoomKeyEntity(
    @PrimaryKey val roomId: Long,
    val keyHex: String,
    val algorithm: String = "aes-256-gcm",
    val source: String,           // "ecies" | "public"
    val createdAt: Long,
    val rotatedAt: Long? = null,
)
