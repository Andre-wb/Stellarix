package sol.vortexx.android.premium.impl

import io.ktor.client.call.body
import io.ktor.client.request.*
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.premium.api.CheckoutSession
import sol.vortexx.android.premium.api.Premium
import sol.vortexx.android.premium.api.PremiumStatus
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpPremium @Inject constructor(
    private val http: VortexHttpClient,
) : Premium {
    @Serializable private data class StartBody(val tier: String)
    @Serializable private data class OkResp(val ok: Boolean)

    override suspend fun status(): PremiumStatus? = runCatching {
        val resp = http.client.get("api/premium/status")
        if (!resp.status.isSuccess()) null else resp.body<PremiumStatus>()
    }.getOrNull()

    override suspend fun startCheckout(tier: String): CheckoutSession? = runCatching {
        val resp = http.client.post("api/premium/checkout") {
            contentType(ContentType.Application.Json)
            setBody(StartBody(tier))
        }
        if (!resp.status.isSuccess()) null else resp.body<CheckoutSession>()
    }.getOrNull()

    override suspend fun cancel(): Boolean = runCatching {
        val resp = http.client.post("api/premium/cancel")
        resp.status.isSuccess() && resp.body<OkResp>().ok
    }.getOrDefault(false)
}
