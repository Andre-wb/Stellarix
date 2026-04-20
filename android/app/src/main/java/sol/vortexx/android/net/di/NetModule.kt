package sol.vortexx.android.net.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.net.api.BaseUrlProvider
import sol.vortexx.android.net.impl.BaseUrlProviderFromPrefs
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class NetModule {

    // `AuthTokenSource` binding lives in auth/di/AuthModule.kt — keeping
    // both here would be a duplicate-binding error in Hilt. The two
    // modules are always in the same graph, so the split is purely by
    // feature, not lifecycle.

    @Binds @Singleton
    abstract fun bindBaseUrlProvider(impl: BaseUrlProviderFromPrefs): BaseUrlProvider
}
