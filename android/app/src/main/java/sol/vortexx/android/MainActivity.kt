package sol.vortexx.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import dagger.hilt.android.AndroidEntryPoint
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.ui.nav.VortexNavHost
import sol.vortexx.android.ui.theme.VortexTheme
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var authRepo: AuthRepository

    // Deep-link target lifted to the activity level so `onNewIntent()`
    // (a new push-tap while the process is alive) can flip the state
    // and force recomposition. A `remember { }` inside setContent only
    // runs once, which would drop the new intent silently.
    private var pendingRoomId by mutableStateOf<Long?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        pendingRoomId = parseDeepLinkRoomId(intent)
        setContent {
            VortexTheme {
                VortexNavHost(
                    authRepo = authRepo,
                    initialRoomId = pendingRoomId,
                    onConsumedInitial = { pendingRoomId = null },
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        pendingRoomId = parseDeepLinkRoomId(intent)
    }

    private fun parseDeepLinkRoomId(intent: Intent?): Long? {
        val data = intent?.data ?: return null
        if (data.scheme != "vortex" || data.host != "chat") return null
        val seg = data.pathSegments.firstOrNull() ?: return null
        return seg.toLongOrNull()
    }
}
