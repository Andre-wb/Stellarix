package sol.vortexx.android.reactions.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.reactions.api.Reactions
import sol.vortexx.android.reactions.impl.InMemoryReactions
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class ReactionsModule {
    @Binds @Singleton
    abstract fun bindReactions(impl: InMemoryReactions): Reactions
}
