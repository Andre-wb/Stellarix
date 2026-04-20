package sol.vortexx.android.feeds.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.feeds.api.ChannelFeedRepository
import sol.vortexx.android.feeds.impl.HttpChannelFeedRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class FeedsModule {
    @Binds @Singleton
    abstract fun bindFeeds(impl: HttpChannelFeedRepository): ChannelFeedRepository
}
