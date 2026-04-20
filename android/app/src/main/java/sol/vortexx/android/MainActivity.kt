package sol.vortexx.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import dagger.hilt.android.AndroidEntryPoint
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.ui.nav.VortexNavHost
import sol.vortexx.android.ui.theme.VortexTheme
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var authRepo: AuthRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            VortexTheme {
                VortexNavHost(authRepo = authRepo)
            }
        }
    }
}
