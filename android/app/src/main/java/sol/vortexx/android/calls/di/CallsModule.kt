package sol.vortexx.android.calls.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.calls.api.CallController
import sol.vortexx.android.calls.api.IceConfigProvider
import sol.vortexx.android.calls.impl.HttpIceConfigProvider
import sol.vortexx.android.calls.impl.WebRtcCallController
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class CallsModule {
    @Binds @Singleton
    abstract fun bindCallController(impl: WebRtcCallController): CallController

    @Binds @Singleton
    abstract fun bindIceConfig(impl: HttpIceConfigProvider): IceConfigProvider
}
