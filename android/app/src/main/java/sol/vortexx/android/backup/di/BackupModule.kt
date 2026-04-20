package sol.vortexx.android.backup.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.backup.api.KeyBackup
import sol.vortexx.android.backup.impl.HttpKeyBackup
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class BackupModule {
    @Binds @Singleton
    abstract fun bindKeyBackup(impl: HttpKeyBackup): KeyBackup
}
