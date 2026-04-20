package sol.vortexx.android.search.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.search.api.SearchRepository
import sol.vortexx.android.search.impl.Fts4SearchRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class SearchModule {
    @Binds @Singleton
    abstract fun bindSearch(impl: Fts4SearchRepository): SearchRepository
}
