package sol.vortexx.android.net.impl

import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpRequestRetry
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logger
import io.ktor.client.plugins.logging.Logging
import io.ktor.client.request.header
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.takeFrom
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import sol.vortexx.android.net.api.AuthTokenSource
import sol.vortexx.android.net.api.BaseUrlProvider
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Single shared Ktor HttpClient for the whole app.
 *
 * The client is parameterised via injected abstractions only:
 *   - [BaseUrlProvider] drives every relative URL request against the
 *     currently-chosen node.
 *   - [AuthTokenSource] supplies the bearer token and a refresh hook,
 *     wired into a 401-retry observer so an expired JWT transparently
 *     triggers a refresh-then-retry once per request.
 *
 * Consumers never see OkHttp or Ktor plugins directly — they receive the
 * pre-configured [HttpClient] through Hilt. Swapping engines later
 * (e.g. CIO for lower memory) is a one-line change in this file.
 */
@Singleton
class VortexHttpClient @Inject constructor(
    private val baseUrlProvider: BaseUrlProvider,
    private val tokens: AuthTokenSource,
) {
    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls     = false
        isLenient         = true
    }

    val client: HttpClient = HttpClient(OkHttp) {
        install(ContentNegotiation) { json(json) }

        install(HttpTimeout) {
            requestTimeoutMillis = 15_000
            connectTimeoutMillis = 5_000
            socketTimeoutMillis  = 15_000
        }

        // Retry: transient 5xx + network blips. Explicit conditions — never
        // retry 4xx (bad request) because that's a client bug, not flakiness.
        install(HttpRequestRetry) {
            retryOnServerErrors(maxRetries = 2)
            retryOnExceptionIf(maxRetries = 2) { _, cause ->
                cause is java.io.IOException
            }
            exponentialDelay(base = 2.0, maxDelayMs = 3_000)
        }

        install(Logging) {
            level = LogLevel.INFO
            logger = object : Logger {
                override fun log(message: String) { android.util.Log.d("VortexHttp", message) }
            }
        }

        // Default request hook: every call gets the current base URL (if
        // bootstrap finished) and an Authorization header (if logged in).
        defaultRequest {
            val base = runCatchingSuspend { baseUrlProvider.current() }
            if (!base.isNullOrBlank()) url.takeFrom(base + "/")
            val token = runCatchingSuspend { tokens.accessToken() }
            if (!token.isNullOrBlank()) header(HttpHeaders.Authorization, "Bearer $token")
        }
    }

    /**
     * Wraps any call that may surface a 401; on expiry runs the refresh
     * hook once and re-executes the block. Call sites use it explicitly
     * instead of a hidden request-pipeline interceptor so the retry
     * boundary is visible in stack traces.
     */
    suspend fun <T> withAuthRetry(block: suspend () -> HttpResponse): HttpResponse {
        val first = block()
        if (first.status != HttpStatusCode.Unauthorized) return first
        val refreshed = runCatchingSuspend { tokens.refresh() } ?: false
        return if (refreshed) block() else first
    }
}

/** Swallows exceptions from a suspending expression (for non-critical paths). */
private suspend inline fun <T> runCatchingSuspend(block: suspend () -> T): T? = try {
    block()
} catch (t: Throwable) {
    null
}
