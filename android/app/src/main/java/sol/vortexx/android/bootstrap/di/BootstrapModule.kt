package sol.vortexx.android.bootstrap.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.bootstrap.api.NodeDirectory
import sol.vortexx.android.bootstrap.api.NodePreferences
import sol.vortexx.android.bootstrap.impl.DataStoreNodePreferences
import sol.vortexx.android.bootstrap.impl.HttpNodeDirectory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class BootstrapModule {

    @Binds @Singleton
    abstract fun bindNodeDirectory(impl: HttpNodeDirectory): NodeDirectory

    @Binds @Singleton
    abstract fun bindNodePreferences(impl: DataStoreNodePreferences): NodePreferences
}
