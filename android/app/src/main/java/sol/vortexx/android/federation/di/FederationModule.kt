package sol.vortexx.android.federation.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.federation.api.MirrorDirectory
import sol.vortexx.android.federation.impl.HttpMirrorDirectory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class FederationModule {
    @Binds @Singleton
    abstract fun bindMirrorDirectory(impl: HttpMirrorDirectory): MirrorDirectory
}
