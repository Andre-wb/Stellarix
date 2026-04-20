package sol.vortexx.android.push.api

/**
 * Wave 18 push notifications.
 *
 * Implementation registers with FCM, obtains the token, posts it (plus the
 * VAPID server key the node advertises) to `/api/push/subscribe`. The
 * server encrypts the push payload with the subscription's p256dh+auth
 * pair so even Google cannot read the content.
 */
interface PushSubscriber {
    suspend fun enable(): Boolean
    suspend fun disable(): Boolean
}
