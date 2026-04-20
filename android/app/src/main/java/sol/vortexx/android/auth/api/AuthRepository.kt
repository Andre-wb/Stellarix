package sol.vortexx.android.auth.api

import kotlinx.coroutines.flow.Flow

/**
 * Auth feature contract. The UI layer depends on this interface only —
 * the impl knows Ktor, JSON, and the endpoint shape.
 */
interface AuthRepository {

    val session: Flow<Session>

    suspend fun register(username: String, password: CharArray): AuthResult
    suspend fun login(username: String, password: CharArray): AuthResult
    suspend fun logout()
}

sealed interface AuthResult {
    data object Ok : AuthResult
    data class Error(val code: String, val message: String) : AuthResult
}

sealed interface Session {
    data object LoggedOut : Session
    data class LoggedIn(val username: String) : Session
}
