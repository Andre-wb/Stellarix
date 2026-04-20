package sol.vortexx.android.spaces.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.spaces.api.SpacesRepository
import sol.vortexx.android.spaces.impl.HttpSpacesRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class SpacesModule {
    @Binds @Singleton
    abstract fun bindSpaces(impl: HttpSpacesRepository): SpacesRepository
}
