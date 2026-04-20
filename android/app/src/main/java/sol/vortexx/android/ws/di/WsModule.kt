package sol.vortexx.android.ws.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.ws.api.WsClient
import sol.vortexx.android.ws.impl.KtorWsClient
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class WsModule {
    @Binds @Singleton
    abstract fun bindWsClient(impl: KtorWsClient): WsClient
}
