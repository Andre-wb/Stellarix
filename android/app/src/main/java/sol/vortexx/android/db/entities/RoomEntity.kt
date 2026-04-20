package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Local mirror of a server-side room. Only fields the client needs to
 * render / route — anti-spam config, federation plumbing, etc. live on
 * the node and are not cached here.
 *
 * `isPrivate = false` is the switch that tells the client whether to
 * pull the Variant-B plaintext key from `/api/rooms/{id}/public-key`
 * (fast path) or go through ECIES (slow path, private rooms).
 */
@Entity(tableName = "rooms")
data class RoomEntity(
    @PrimaryKey val id: Long,
    val name: String,
    val description: String = "",
    val inviteCode: String,
    val isPrivate: Boolean,
    val isChannel: Boolean = false,
    val isDm: Boolean = false,
    val avatarEmoji: String = "\uD83D\uDCAC",
    val memberCount: Int = 0,
    val unreadCount: Int = 0,
    val lastMessageAt: Long? = null,      // epoch millis, null = no messages yet
)
