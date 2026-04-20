package sol.vortexx.android.auth.impl

import sol.vortexx.android.auth.api.SecureStore
import sol.vortexx.android.net.api.AuthTokenSource
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Reads JWTs that [AuthRepositoryImpl] wrote to [SecureStore].
 *
 * Wave 4's NullAuthTokenSource binding is replaced by this one in the
 * auth DI module — a single @Binds swap, zero consumer changes.
 */
@Singleton
class SecureStoreAuthTokenSource @Inject constructor(
    private val store: SecureStore,
    private val repo: dagger.Lazy<AuthRepositoryImpl>,
) : AuthTokenSource {

    override suspend fun accessToken():  String? = store.getString(KEY_ACCESS)
    override suspend fun refreshToken(): String? = store.getString(KEY_REFRESH)

    /** Delegates to the repo, which calls POST /api/auth/refresh. */
    override suspend fun refresh(): Boolean = repo.get().refreshTokens()

    companion object {
        const val KEY_ACCESS  = "jwt_access"
        const val KEY_REFRESH = "jwt_refresh"
        const val KEY_USER    = "jwt_username"
    }
}
