package sol.vortexx.android.identity.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.identity.api.IdentityRepository
import sol.vortexx.android.identity.api.SeedProvider
import sol.vortexx.android.identity.impl.Bip39SeedProvider
import sol.vortexx.android.identity.impl.SeedIdentityRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class IdentityModule {

    @Binds @Singleton
    abstract fun bindSeedProvider(impl: Bip39SeedProvider): SeedProvider

    @Binds @Singleton
    abstract fun bindIdentityRepository(impl: SeedIdentityRepository): IdentityRepository
}
