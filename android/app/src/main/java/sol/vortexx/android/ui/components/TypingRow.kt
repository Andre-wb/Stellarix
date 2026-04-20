package sol.vortexx.android.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * "X is typing…" row. Hidden when nobody is typing; fades in/out smoothly
 * driven by [users] which is the already-pruned snapshot from
 * [sol.vortexx.android.chat.api.Presence.typingIn].
 */
@Composable
fun TypingRow(users: Set<String>, modifier: Modifier = Modifier) {
    AnimatedVisibility(
        visible = users.isNotEmpty(),
        enter = fadeIn(), exit = fadeOut(),
        modifier = modifier,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0x22000000))
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val label = when (users.size) {
                0 -> ""
                1 -> "${users.first()} is typing…"
                2 -> "${users.joinToString(" and ")} are typing…"
                else -> "${users.take(2).joinToString(", ")} and ${users.size - 2} more are typing…"
            }
            Text(label,
                 style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
