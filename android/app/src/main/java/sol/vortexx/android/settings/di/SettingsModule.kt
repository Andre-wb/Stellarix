package sol.vortexx.android.settings.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.settings.api.SettingsStore
import sol.vortexx.android.settings.impl.DataStoreSettingsStore
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class SettingsModule {
    @Binds @Singleton
    abstract fun bindSettings(impl: DataStoreSettingsStore): SettingsStore
}
