package sol.vortexx.android.db

import androidx.room.Database
import androidx.room.RoomDatabase
import sol.vortexx.android.db.dao.BotDao
import sol.vortexx.android.db.dao.ChannelFeedDao
import sol.vortexx.android.db.dao.MemberDao
import sol.vortexx.android.db.dao.MessageDao
import sol.vortexx.android.db.dao.ReactionDao
import sol.vortexx.android.db.dao.ReadReceiptDao
import sol.vortexx.android.db.dao.RoomDao
import sol.vortexx.android.db.dao.RoomKeyDao
import sol.vortexx.android.db.dao.SearchDao
import sol.vortexx.android.db.dao.SpaceDao
import sol.vortexx.android.db.dao.ThreadDao
import sol.vortexx.android.db.dao.UserDao
import sol.vortexx.android.db.entities.BotEntity
import sol.vortexx.android.db.entities.ChannelFeedEntity
import sol.vortexx.android.db.entities.MemberEntity
import sol.vortexx.android.db.entities.MessageEntity
import sol.vortexx.android.db.entities.MessageFts
import sol.vortexx.android.db.entities.ReactionEntity
import sol.vortexx.android.db.entities.ReadReceiptEntity
import sol.vortexx.android.db.entities.RoomEntity
import sol.vortexx.android.db.entities.RoomKeyEntity
import sol.vortexx.android.db.entities.SpaceEntity
import sol.vortexx.android.db.entities.ThreadEntity
import sol.vortexx.android.db.entities.UserEntity

@Database(
    entities = [
        RoomEntity::class,
        MemberEntity::class,
        MessageEntity::class,
        MessageFts::class,
        RoomKeyEntity::class,
        UserEntity::class,
        ReactionEntity::class,
        SpaceEntity::class,
        BotEntity::class,
        ThreadEntity::class,
        ChannelFeedEntity::class,
        ReadReceiptEntity::class,
    ],
    version = 4,
    exportSchema = false,
)
abstract class VortexDatabase : RoomDatabase() {
    abstract fun rooms():     RoomDao
    abstract fun members():   MemberDao
    abstract fun messages():  MessageDao
    abstract fun roomKeys():  RoomKeyDao
    abstract fun users():     UserDao
    abstract fun reactions(): ReactionDao
    abstract fun spaces():    SpaceDao
    abstract fun bots():      BotDao
    abstract fun search():    SearchDao
    abstract fun threads():   ThreadDao
    abstract fun feeds():     ChannelFeedDao
    abstract fun receipts():  ReadReceiptDao
}
