package sol.vortexx.android.chat.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.chat.api.IncomingMessages
import sol.vortexx.android.chat.api.MessageActions
import sol.vortexx.android.chat.api.MessageSender
import sol.vortexx.android.chat.api.Presence
import sol.vortexx.android.chat.impl.ChatEngine
import sol.vortexx.android.chat.impl.MessageActionsImpl
import sol.vortexx.android.chat.impl.PresenceImpl
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class ChatModule {
    @Binds @Singleton abstract fun bindSender(impl: ChatEngine): MessageSender
    @Binds @Singleton abstract fun bindIncoming(impl: ChatEngine): IncomingMessages
    @Binds @Singleton abstract fun bindActions(impl: MessageActionsImpl): MessageActions
    @Binds @Singleton abstract fun bindPresence(impl: PresenceImpl): Presence
}
