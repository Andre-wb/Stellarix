package sol.vortexx.android.push.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.push.api.PushSubscriber
import sol.vortexx.android.push.impl.FcmPushSubscriber
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class PushModule {
    @Binds @Singleton
    abstract fun bindPushSubscriber(impl: FcmPushSubscriber): PushSubscriber
}
