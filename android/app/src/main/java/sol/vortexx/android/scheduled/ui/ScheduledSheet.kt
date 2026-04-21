package sol.vortexx.android.scheduled.ui

import android.app.TimePickerDialog
import android.icu.text.SimpleDateFormat
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.scheduled.api.ScheduledMessage
import sol.vortexx.android.scheduled.api.ScheduledMessages
import java.util.*
import javax.inject.Inject

/**
 * Bottom sheet listing this room's scheduled messages + a minimal
 * "schedule at HH:mm" entrypoint. The composer itself handles the
 * encrypt-then-POST; this UI just shows queued items and cancellation.
 */
@HiltViewModel
class ScheduledViewModel @Inject constructor(
    private val repo: ScheduledMessages,
) : ViewModel() {
    private val _items = MutableStateFlow<List<ScheduledMessage>>(emptyList())
    val items = _items.asStateFlow()

    fun load(roomId: Long) = viewModelScope.launch {
        _items.value = repo.list(roomId)
    }

    fun cancel(id: Long) = viewModelScope.launch {
        repo.cancel(id)
        _items.value = _items.value.filterNot { it.id == id }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScheduledSheet(
    roomId: Long,
    onDismiss: () -> Unit,
    onPickSendAt: (Long) -> Unit,
    vm: ScheduledViewModel = hiltViewModel(),
) {
    val items by vm.items.collectAsState()
    val ctx = LocalContext.current
    LaunchedEffect(roomId) { vm.load(roomId) }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Scheduled", style = MaterialTheme.typography.titleMedium,
                     fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                TextButton(onClick = {
                    val now = Calendar.getInstance()
                    TimePickerDialog(ctx, { _, hh, mm ->
                        val c = Calendar.getInstance().apply {
                            set(Calendar.HOUR_OF_DAY, hh); set(Calendar.MINUTE, mm)
                            set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
                            if (timeInMillis < System.currentTimeMillis()) add(Calendar.DAY_OF_YEAR, 1)
                        }
                        onPickSendAt(c.timeInMillis)
                        onDismiss()
                    }, now.get(Calendar.HOUR_OF_DAY), now.get(Calendar.MINUTE), true).show()
                }) { Text("Schedule new") }
            }
            if (items.isEmpty()) {
                Text("No scheduled messages",
                     color = MaterialTheme.colorScheme.onSurfaceVariant,
                     modifier = Modifier.padding(16.dp))
            } else LazyColumn {
                items(items, key = ScheduledMessage::id) { m ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                SimpleDateFormat("dd.MM HH:mm", Locale.getDefault())
                                    .format(Date(m.send_at)),
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold,
                            )
                            Text(
                                "ciphertext ${m.ciphertext_b64.take(24)}…",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        IconButton(onClick = { vm.cancel(m.id) }) {
                            Icon(Icons.Filled.Close, contentDescription = "Cancel")
                        }
                    }
                }
            }
        }
    }
}
