package sol.vortexx.android.multidevice.impl

import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.multidevice.api.DeviceLinker
import sol.vortexx.android.multidevice.api.LinkCode
import sol.vortexx.android.multidevice.api.RedeemResult
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpDeviceLinker @Inject constructor(
    private val http: VortexHttpClient,
) : DeviceLinker {

    override suspend fun generateCode(): LinkCode? = runCatching {
        val resp = http.client.post("api/multidevice/link/new")
        if (!resp.status.isSuccess()) return@runCatching null
        val body = resp.body<LinkResp>()
        LinkCode(code = body.code, expiresAt = body.expires_at)
    }.getOrNull()

    override suspend fun redeemCode(code: String, newDevicePubHex: String): RedeemResult = runCatching {
        val resp = http.client.post("api/multidevice/link/redeem") {
            contentType(ContentType.Application.Json)
            setBody(RedeemReq(code = code, new_device_pub = newDevicePubHex))
        }
        if (!resp.status.isSuccess()) {
            RedeemResult.Error("http_${resp.status.value}")
        } else {
            RedeemResult.Ok(encryptedKeysBlob = resp.body<RedeemResp>().encrypted_keys)
        }
    }.getOrElse { RedeemResult.Error(it.message ?: "io") }

    @Serializable private data class LinkResp(val code: String, val expires_at: Long)
    @Serializable private data class RedeemReq(val code: String, val new_device_pub: String)
    @Serializable private data class RedeemResp(val encrypted_keys: String)
}
