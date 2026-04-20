package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "spaces")
data class SpaceEntity(
    @PrimaryKey val id: Long,
    val name: String,
    val ownerId: Long,
    val avatarEmoji: String = "\uD83C\uDF0C",
    val memberCount: Int = 0,
    val isPublic: Boolean = false,
)
