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
import sol.vortexx.android.net.impl.VortexHttpClient
import sol.vortexx.android.push.api.PushSubscriber
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * FCM-backed [PushSubscriber].
 *
 * enable():
 *   1. Ask Firebase for the instance token
 *   2. POST it (as `endpoint`) to /api/push/subscribe along with placeholder
 *      p256dh/auth. The node wraps the token in its own VAPID envelope so
 *      Google can only see the opaque payload, never plaintext.
 */
@Singleton
class FcmPushSubscriber @Inject constructor(
    private val http: VortexHttpClient,
) : PushSubscriber {

    override suspend fun enable(): Boolean = runCatching {
        val token = fetchFcmToken() ?: return false
        val resp = http.client.post("api/push/subscribe") {
            contentType(ContentType.Application.Json)
            setBody(SubscribeReq(
                endpoint = "fcm://$token",
                p256dh = "",     // FCM doesn't expose subscription key material
                auth = "",
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
