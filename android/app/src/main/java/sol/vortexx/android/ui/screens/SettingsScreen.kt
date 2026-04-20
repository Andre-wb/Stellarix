package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.identity.api.IdentityRepository
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val auth: AuthRepository,
    private val identity: IdentityRepository,
) : ViewModel() {
    fun logout() { viewModelScope.launch { auth.logout() } }
    fun wipe()   { viewModelScope.launch { identity.wipe(); auth.logout() } }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(onBack: () -> Unit, vm: SettingsViewModel = hiltViewModel()) {
    var notifications by remember { mutableStateOf(true) }
    var showPanicConfirm by remember { mutableStateOf(false) }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Notifications",
                         style = MaterialTheme.typography.bodyLarge,
                         color = MaterialTheme.colorScheme.onBackground)
                    Text("Push alerts on incoming messages",
                         style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(checked = notifications, onCheckedChange = { notifications = it })
            }
            HorizontalDivider()

            SettingsRow(
                title = "Sign out",
                subtitle = "Keeps local data; asks to log back in",
                onClick = { vm.logout() },
            )
            HorizontalDivider()

            SettingsRow(
                title = "Panic — wipe everything",
                subtitle = "Deletes local keys, messages and session. Cannot be undone.",
                danger = true,
                onClick = { showPanicConfirm = true },
            )
        }
    }

    if (showPanicConfirm) AlertDialog(
        onDismissRequest = { showPanicConfirm = false },
        title = { Text("Wipe all local data?") },
        text  = { Text("Your identity, message cache and session will be destroyed. " +
                       "The server-side panic action is NOT triggered — use /api/panic for that.") },
        confirmButton = {
            TextButton(onClick = { showPanicConfirm = false; vm.wipe() }) {
                Text("Wipe", color = MaterialTheme.colorScheme.error)
            }
        },
        dismissButton = { TextButton(onClick = { showPanicConfirm = false }) { Text("Cancel") } },
    )
}

@Composable
private fun SettingsRow(title: String, subtitle: String, onClick: () -> Unit, danger: Boolean = false) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(16.dp),
    ) {
        Text(
            title,
            style = MaterialTheme.typography.bodyLarge,
            color = if (danger) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onBackground,
        )
        Text(
            subtitle,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
