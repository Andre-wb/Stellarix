package sol.vortexx.android.auth.impl

import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.auth.api.AuthResult
import sol.vortexx.android.auth.api.SecureStore
import sol.vortexx.android.auth.api.Session
import sol.vortexx.android.auth.impl.SecureStoreAuthTokenSource.Companion.KEY_ACCESS
import sol.vortexx.android.auth.impl.SecureStoreAuthTokenSource.Companion.KEY_REFRESH
import sol.vortexx.android.auth.impl.SecureStoreAuthTokenSource.Companion.KEY_USER
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Concrete [AuthRepository] — the only class that talks to
 * `/api/auth/*` on the node. Everything else consumes [Session] and
 * [AuthResult] through the interface, so the API shape can change here
 * without rippling.
 */
@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val http: VortexHttpClient,
    private val store: SecureStore,
) : AuthRepository {

    private val _session = MutableStateFlow<Session>(initialSession())
    override val session = _session.asStateFlow()

    override suspend fun register(username: String, password: CharArray): AuthResult =
        authCall(path = "api/authentication/register", username = username, password = password)

    override suspend fun login(username: String, password: CharArray): AuthResult =
        authCall(path = "api/authentication/login", username = username, password = password)

    override suspend fun logout() {
        store.putString(KEY_ACCESS, null)
        store.putString(KEY_REFRESH, null)
        store.putString(KEY_USER, null)
        _session.value = Session.LoggedOut
    }

    /** Called by the net layer on 401 — tries to mint new tokens. */
    suspend fun refreshTokens(): Boolean {
        val rt = store.getString(KEY_REFRESH) ?: return false
        return runCatching {
            val resp = http.client.post("api/authentication/refresh") {
                contentType(ContentType.Application.Json)
                setBody(RefreshReq(rt))
            }
            if (!resp.status.isSuccess()) return@runCatching false
            val body = resp.body<AuthResp>()
            store.putString(KEY_ACCESS, body.access_token)
            body.refresh_token?.let { store.putString(KEY_REFRESH, it) }
            true
        }.getOrDefault(false)
    }

    // ── internals ──────────────────────────────────────────────────────

    private suspend fun authCall(path: String, username: String, password: CharArray): AuthResult {
        val pwStr = String(password)   // Kotlin String is interned; next line zeroes the char[].
        try {
            val resp = http.client.post(path) {
                contentType(ContentType.Application.Json)
                setBody(AuthReq(username, pwStr))
            }
            if (!resp.status.isSuccess()) {
                return AuthResult.Error(
                    code = "http_${resp.status.value}",
                    message = resp.bodyAsText().take(200),
                )
            }
            val body = resp.body<AuthResp>()
            store.putString(KEY_ACCESS,  body.access_token)
            store.putString(KEY_REFRESH, body.refresh_token)
            store.putString(KEY_USER,    username)
            _session.value = Session.LoggedIn(username)
            return AuthResult.Ok
        } catch (t: Throwable) {
            return AuthResult.Error(code = "io", message = t.message ?: "request failed")
        } finally {
            password.fill('\u0000')
        }
    }

    private fun initialSession(): Session {
        val u = store.getString(KEY_USER)
        return if (u != null && store.getString(KEY_ACCESS) != null)
            Session.LoggedIn(u) else Session.LoggedOut
    }

    @Serializable private data class AuthReq(val username: String, val password: String)
    @Serializable private data class RefreshReq(val refresh_token: String)
    @Serializable private data class AuthResp(
        val access_token: String,
        val refresh_token: String? = null,
    )
}
