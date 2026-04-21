package sol.vortexx.android.accounts.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.accounts.api.Accounts
import sol.vortexx.android.accounts.impl.VortexAccounts
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class AccountsModule {
    @Binds @Singleton
    abstract fun bindAccounts(impl: VortexAccounts): Accounts
}
