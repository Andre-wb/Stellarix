package sol.vortexx.android.ui.components

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * "Seen by N" pill under an outgoing bubble.
 *
 * @param messageId    the bubble's message id (check against the read map).
 * @param readThrough  userId → latest read messageId, snapshot from [Presence.readUpTo].
 *
 * No special rendering for self — ChatScreen only instantiates this on
 * outgoing bubbles (senderId matches the local user).
 */
@Composable
fun ReadReceiptsPill(
    messageId: Long,
    readThrough: Map<Long, Long>,
    modifier: Modifier = Modifier,
) {
    val seen = readThrough.count { (_, lastRead) -> lastRead >= messageId }
    if (seen <= 0) return

    Text(
        text = "seen by $seen",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier.padding(top = 2.dp),
    )
}
