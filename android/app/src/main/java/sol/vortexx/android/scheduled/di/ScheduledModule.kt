package sol.vortexx.android.scheduled.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.scheduled.api.ScheduledMessages
import sol.vortexx.android.scheduled.impl.HttpScheduled
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class ScheduledModule {
    @Binds @Singleton
    abstract fun bindScheduled(impl: HttpScheduled): ScheduledMessages
}
