package sol.vortexx.android.folders.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.folders.api.Folders
import sol.vortexx.android.folders.impl.PrefsFolders
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class FoldersModule {
    @Binds @Singleton
    abstract fun bindFolders(impl: PrefsFolders): Folders
}
