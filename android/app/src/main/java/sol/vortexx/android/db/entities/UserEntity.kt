package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Known-user cache. Populated opportunistically — every time we see a
 * new sender/member the client upserts. Used for avatar + fingerprint
 * lookup; authoritative source of truth remains the node.
 */
@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey val id: Long,
    val username: String,
    val displayName: String? = null,
    val x25519PubHex: String? = null,
    val ed25519PubHex: String? = null,
    val avatarEmoji: String? = null,
)
