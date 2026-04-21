package sol.vortexx.android.premium.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.premium.api.Premium
import sol.vortexx.android.premium.impl.HttpPremium
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class PremiumModule {
    @Binds @Singleton
    abstract fun bindPremium(impl: HttpPremium): Premium
}
