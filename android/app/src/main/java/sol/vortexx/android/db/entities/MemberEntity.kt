package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

/**
 * Room membership — one row per (roomId, userId).
 * Hard FK into [RoomEntity] so a room delete cascades to its members.
 */
@Entity(
    tableName = "members",
    primaryKeys = ["roomId", "userId"],
    foreignKeys = [
        ForeignKey(
            entity = RoomEntity::class,
            parentColumns = ["id"],
            childColumns  = ["roomId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("userId")],
)
data class MemberEntity(
    val roomId: Long,
    val userId: Long,
    val username: String,
    val role: String,                 // "owner" | "admin" | "member"
    val x25519PubHex: String? = null,
)
