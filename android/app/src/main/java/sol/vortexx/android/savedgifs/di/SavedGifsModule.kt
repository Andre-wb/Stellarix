package sol.vortexx.android.savedgifs.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.savedgifs.api.SavedGifs
import sol.vortexx.android.savedgifs.impl.HttpSavedGifs
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class SavedGifsModule {
    @Binds @Singleton
    abstract fun bindSavedGifs(impl: HttpSavedGifs): SavedGifs
}
