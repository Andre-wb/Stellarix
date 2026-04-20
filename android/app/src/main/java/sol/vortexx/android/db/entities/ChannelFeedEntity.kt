package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

/** RSS / Atom feed subscription for a channel. */
@Entity(
    tableName = "channel_feeds",
    foreignKeys = [
        ForeignKey(
            entity = RoomEntity::class,
            parentColumns = ["id"],
            childColumns = ["roomId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("roomId")],
)
data class ChannelFeedEntity(
    @PrimaryKey val id: Long,
    val roomId: Long,
    val feedType: String,            // "rss" | "atom" | "json"
    val url: String,
    val lastFetched: Long? = null,
    val isActive: Boolean = true,
)
