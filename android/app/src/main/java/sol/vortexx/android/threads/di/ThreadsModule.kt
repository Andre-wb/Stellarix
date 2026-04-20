package sol.vortexx.android.threads.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.threads.api.ThreadsRepository
import sol.vortexx.android.threads.impl.HttpThreadsRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class ThreadsModule {
    @Binds @Singleton
    abstract fun bindThreads(impl: HttpThreadsRepository): ThreadsRepository
}
