package sol.vortexx.android.db.di

import android.content.Context
import androidx.room.Room
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.db.VortexDatabase
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
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides @Singleton
    fun provideDb(@ApplicationContext ctx: Context): VortexDatabase =
        Room.databaseBuilder(ctx, VortexDatabase::class.java, "vortex.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides fun rooms(db: VortexDatabase):     RoomDao     = db.rooms()
    @Provides fun members(db: VortexDatabase):   MemberDao   = db.members()
    @Provides fun messages(db: VortexDatabase):  MessageDao  = db.messages()
    @Provides fun roomKeys(db: VortexDatabase):  RoomKeyDao  = db.roomKeys()
    @Provides fun users(db: VortexDatabase):     UserDao     = db.users()
    @Provides fun reactions(db: VortexDatabase): ReactionDao = db.reactions()
    @Provides fun spaces(db: VortexDatabase):    SpaceDao    = db.spaces()
    @Provides fun bots(db: VortexDatabase):      BotDao      = db.bots()
    @Provides fun search(db: VortexDatabase):    SearchDao   = db.search()
    @Provides fun threads(db: VortexDatabase):   ThreadDao   = db.threads()
    @Provides fun feeds(db: VortexDatabase):     ChannelFeedDao = db.feeds()
    @Provides fun receipts(db: VortexDatabase):  ReadReceiptDao = db.receipts()
}
