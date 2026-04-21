package sol.vortexx.android.premium.api

import kotlinx.serialization.Serializable

@Serializable
data class PremiumStatus(
    val tier: String,
    val renews_at: Long? = null,
    val cancelled_at: Long? = null,
    val features: List<String> = emptyList(),
)

@Serializable
data class CheckoutSession(val url: String, val id: String)

interface Premium {
    suspend fun status(): PremiumStatus?
    suspend fun startCheckout(tier: String): CheckoutSession?
    suspend fun cancel(): Boolean
}
