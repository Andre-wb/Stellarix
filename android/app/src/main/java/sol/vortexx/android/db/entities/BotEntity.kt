package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "bots")
data class BotEntity(
    @PrimaryKey val id: Long,
    val name: String,
    val author: String,
    val shortDescription: String,
    val avatarUrl: String? = null,
    val installed: Boolean = false,
    val rating: Double = 0.0,
    val installCount: Long = 0,
)
