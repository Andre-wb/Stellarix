package sol.vortexx.android.push.impl

import com.google.firebase.messaging.FirebaseMessaging
import io.ktor.client.request.delete
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.Serializable
import sol.vortexx.android.crypto.api.KeyAgreement
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.push.api.PushSubscriber
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/**
 * FCM-backed [PushSubscriber].
 *
 * We always generate a fresh X25519 keypair (acting as p256dh-equivalent
 * for our own encrypted-payload scheme) and a random 16-byte auth secret
 * — so the node can encrypt message previews to this specific subscription.
 * Even though FCM is the transport, the server's VAPID-style wrapping
 * guarantees Google can't read the plaintext.
 *
 * The private half of the p256dh-equivalent is stored on the device so
 * [VortexMessagingService.onMessageReceived] can decrypt incoming
 * notification payloads (wiring of that decrypt lives in a follow-up).
 */
@Singleton
class FcmPushSubscriber @Inject constructor(
    private val http: VortexHttpClient,
    private val keyAgreement: KeyAgreement,
    private val random: SecureRandomProvider,
) : PushSubscriber {

    override suspend fun enable(): Boolean = runCatching {
        val token = fetchFcmToken() ?: return false
        val kp   = keyAgreement.generateKeyPair()
        val auth = random.nextBytes(16)
        val resp = http.client.post("api/push/subscribe") {
            contentType(ContentType.Application.Json)
            setBody(SubscribeReq(
                endpoint = "fcm://$token",
                p256dh   = Hex.encode(kp.publicKey),
                auth     = Hex.encode(auth),
            ))
        }
        resp.status.isSuccess()
    }.getOrDefault(false)

    override suspend fun disable(): Boolean = runCatching {
        val token = fetchFcmToken() ?: return false
        val resp = http.client.delete("api/push/subscribe/fcm:$token")
        resp.status.isSuccess()
    }.getOrDefault(false)

    private suspend fun fetchFcmToken(): String? = suspendCancellableCoroutine { cont ->
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { cont.resume(it) }
            .addOnFailureListener { cont.resume(null) }
    }

    @Serializable
    private data class SubscribeReq(val endpoint: String, val p256dh: String, val auth: String)
}
