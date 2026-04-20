package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import sol.vortexx.android.bots.api.BotsRepository
import sol.vortexx.android.db.entities.BotEntity
import sol.vortexx.android.ui.theme.VortexPurple
import javax.inject.Inject

@HiltViewModel
class BotsViewModel @Inject constructor(private val repo: BotsRepository) : ViewModel() {
    val marketplace = repo.marketplace().stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList(),
    )
    init { viewModelScope.launch { repo.refreshMarketplace() } }

    fun install(id: Long)   { viewModelScope.launch { repo.install(id) } }
    fun uninstall(id: Long) { viewModelScope.launch { repo.uninstall(id) } }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BotsScreen(onBack: () -> Unit, vm: BotsViewModel = hiltViewModel()) {
    val bots by vm.marketplace.collectAsState()
    LaunchedEffect(Unit) { /* pulled by VM init */ }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Bot marketplace") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            items(bots, key = BotEntity::id) { bot ->
                BotRow(bot, onInstall = vm::install, onUninstall = vm::uninstall)
            }
        }
    }
}

@Composable
private fun BotRow(bot: BotEntity, onInstall: (Long) -> Unit, onUninstall: (Long) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(Modifier.weight(1f)) {
            Text(bot.name, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onBackground)
            Text("by ${bot.author}", style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(bot.shortDescription, style = MaterialTheme.typography.bodyMedium,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("★ %.1f · %d installs".format(bot.rating, bot.installCount),
                 style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (bot.installed) OutlinedButton(onClick = { onUninstall(bot.id) }) { Text("Remove") }
        else Button(
            onClick = { onInstall(bot.id) },
            colors = ButtonDefaults.buttonColors(containerColor = VortexPurple),
        ) { Text("Install") }
    }
}
