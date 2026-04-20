package sol.vortexx.android.bootstrap.impl

import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import sol.vortexx.android.bootstrap.api.NodeDirectory
import sol.vortexx.android.bootstrap.api.ProbeResult
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Ktor-backed [NodeDirectory].
 *
 * Wave 3 probes the primary controller URL (hard-coded — DoH/SNS gateway
 * comes in a later wave) via `GET <url>/v1/integrity`. If the response is
 * JSON with `status: "verified"` we treat the node as good; anything else
 * (timeout, non-2xx, malformed body) surfaces as [ProbeResult.Unreachable].
 *
 * The HttpClient here is deliberately minimal — the production network
 * layer with JWT / retries / WebSocket lives in Wave 4. Keeping this one
 * tiny means bootstrap stays decoupled from auth.
 */
@Singleton
class HttpNodeDirectory @Inject constructor() : NodeDirectory {

    private val client = HttpClient(OkHttp) {
        install(HttpTimeout) {
            requestTimeoutMillis = 5_000
            connectTimeoutMillis = 3_000
            socketTimeoutMillis  = 5_000
        }
    }
    private val json = Json { ignoreUnknownKeys = true }

    override suspend fun probePrimary(): ProbeResult = probe(PRIMARY_URL)

    override suspend fun probe(url: String): ProbeResult {
        val clean = normalize(url) ?: return ProbeResult.Unreachable(url, "malformed_url")
        val probeUrl = "$clean/v1/integrity"

        val result = withTimeoutOrNull(7_000) {
            runCatching { client.get(probeUrl) }
        } ?: return ProbeResult.Unreachable(probeUrl, "timeout")

        val resp = result.getOrElse { return ProbeResult.Unreachable(probeUrl, it.message ?: "io_error") }
        if (!resp.status.isSuccess()) return ProbeResult.Unreachable(probeUrl, "http_${resp.status.value}")

        return runCatching {
            val body = json.parseToJsonElement(resp.bodyAsText()).jsonObject
            val status  = body["status"]?.jsonPrimitive?.content
            val version = body["version"]?.jsonPrimitive?.content
            if (status == "verified") ProbeResult.Ok(clean, version)
            else                      ProbeResult.Unreachable(probeUrl, "status_$status")
        }.getOrElse { ProbeResult.Unreachable(probeUrl, "bad_json") }
    }

    private fun normalize(url: String): String? {
        val trimmed = url.trim().trimEnd('/')
        if (trimmed.isEmpty()) return null
        val withScheme = if (trimmed.contains("://")) trimmed else "https://$trimmed"
        return runCatching { java.net.URI(withScheme).also { require(!it.host.isNullOrBlank()) } }
            .map { withScheme }
            .getOrNull()
    }

    private companion object {
        // First-launch target. Wave 19 swaps this for a DoH-resolved
        // rotation of vortexx.sol mirrors.
        const val PRIMARY_URL = "https://vortexx.sol"
    }
}
