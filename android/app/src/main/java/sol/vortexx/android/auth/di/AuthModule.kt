package sol.vortexx.android.auth.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.auth.api.SecureStore
import sol.vortexx.android.auth.impl.AuthRepositoryImpl
import sol.vortexx.android.auth.impl.EncryptedPrefsSecureStore
import sol.vortexx.android.auth.impl.SecureStoreAuthTokenSource
import sol.vortexx.android.net.api.AuthTokenSource
import javax.inject.Singleton

/**
 * Auth wiring. Crucially, this module **overrides** the Wave-4
 * [AuthTokenSource] binding: by installing in the same component with a
 * later classpath order, Hilt picks the concrete secure-store impl at
 * graph resolution time — zero changes to any consumer.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class AuthModule {

    @Binds @Singleton
    abstract fun bindSecureStore(impl: EncryptedPrefsSecureStore): SecureStore

    @Binds @Singleton
    abstract fun bindAuthRepository(impl: AuthRepositoryImpl): AuthRepository

    @Binds @Singleton
    abstract fun bindAuthTokenSource(impl: SecureStoreAuthTokenSource): AuthTokenSource
}
