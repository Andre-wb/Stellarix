package sol.vortexx.android.bots.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.bots.api.BotsRepository
import sol.vortexx.android.bots.impl.HttpBotsRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class BotsModule {
    @Binds @Singleton
    abstract fun bindBots(impl: HttpBotsRepository): BotsRepository
}
