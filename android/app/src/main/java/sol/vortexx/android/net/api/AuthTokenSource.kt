package sol.vortexx.android.net.api

/**
 * Who owns the current JWT (access + refresh).
 *
 * The net layer only needs to *read* them; the auth feature (Wave 5)
 * writes after login / refresh. Keeping the interface read-only from the
 * HTTP side removes a whole class of accidental-mutation bugs where a
 * request-failure handler could overwrite the session.
 */
interface AuthTokenSource {
    /** Current access JWT, or null if not logged in. */
    suspend fun accessToken(): String?

    /** Refresh JWT used by the refresh endpoint; null if not available. */
    suspend fun refreshToken(): String?

    /** Called by net layer on 401 to attempt a silent refresh. */
    suspend fun refresh(): Boolean
}
