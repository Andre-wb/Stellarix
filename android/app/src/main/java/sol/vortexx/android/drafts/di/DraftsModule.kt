package sol.vortexx.android.drafts.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.drafts.api.Drafts
import sol.vortexx.android.drafts.impl.HttpDrafts
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class DraftsModule {
    @Binds @Singleton
    abstract fun bindDrafts(impl: HttpDrafts): Drafts
}
