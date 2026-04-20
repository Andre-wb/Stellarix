package sol.vortexx.android.push.impl

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import sol.vortexx.android.MainActivity
import sol.vortexx.android.R
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject

/**
 * FCM receive path.
 *
 * Incoming push payloads from the Vortex node contain only the minimum:
 *   { title, body, room_id, message_id } — the server must never know
 *   the plaintext message since the node is intentionally blinded to
 *   content by our E2E flow. What the user sees locally is exactly the
 *   title/body the server composed from unencrypted metadata.
 *
 * Deep-link: tapping the notification opens [MainActivity] with a
 * `vortex://chat/<roomId>` data URI that the NavHost can resolve (when
 * we wire that up — for now the activity reopens to its saved state).
 */
@AndroidEntryPoint
class VortexMessagingService : FirebaseMessagingService() {

    @Inject lateinit var http: VortexHttpClient
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // The FcmPushSubscriber re-registers on the next enable() call,
        // so the token change takes effect at login. No action needed here.
    }

    override fun onMessageReceived(message: RemoteMessage) {
        ensureChannel()
        val data = message.data
        val title = data["title"] ?: message.notification?.title ?: "Vortex"
        val body  = data["body"]  ?: message.notification?.body  ?: ""
        val roomId = data["room_id"]?.toLongOrNull()

        val tap = Intent(this, MainActivity::class.java).apply {
            if (roomId != null) data = Uri.parse("vortex://chat/$roomId")
            addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pi = PendingIntent.getActivity(
            this, roomId?.toInt() ?: 0, tap,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        runCatching {
            NotificationManagerCompat.from(this).notify(
                roomId?.toInt() ?: System.currentTimeMillis().toInt(),
                notif,
            )
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (mgr.getNotificationChannel(CHANNEL_ID) != null) return
        mgr.createNotificationChannel(NotificationChannel(
            CHANNEL_ID,
            "Messages",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply { description = "Incoming Vortex messages" })
    }

    companion object { const val CHANNEL_ID = "vortex_messages" }
}
