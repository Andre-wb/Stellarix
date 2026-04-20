package sol.vortexx.android.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val DarkColors = darkColorScheme(
    primary          = VortexPurple,
    onPrimary        = VortexText,
    primaryContainer = VortexPurple,
    secondary        = VortexCyan,
    background       = VortexBg,
    onBackground     = VortexText,
    surface          = VortexBg2,
    onSurface        = VortexText,
    surfaceVariant   = VortexBg3,
    onSurfaceVariant = VortexText2,
    outline          = VortexBorder2,
)

// Light scheme is a near-mirror — the web has a light mode we keep parity
// with. Both currently share the same accent; finer tuning in a later wave.
private val LightColors = lightColorScheme(
    primary          = VortexPurple,
    secondary        = VortexCyan,
)

@Composable
fun VortexTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors

    // Paint the status bar the same as our background so edge-to-edge
    // doesn't flash the default white bar during cold launch.
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val win = (view.context as Activity).window
            win.statusBarColor = colors.background.toArgb()
            WindowCompat.getInsetsController(win, view)
                .isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colors,
        typography  = VortexTypography,
        content     = content,
    )
}
