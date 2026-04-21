package sol.vortexx.android.premium.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
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
import sol.vortexx.android.premium.api.CheckoutSession
import sol.vortexx.android.premium.api.Premium
import sol.vortexx.android.premium.api.PremiumStatus
import javax.inject.Inject

@HiltViewModel
class PremiumViewModel @Inject constructor(
    private val repo: Premium,
) : ViewModel() {
    private val _status = MutableStateFlow<PremiumStatus?>(null)
    val status = _status.asStateFlow()
    private val _checkout = MutableStateFlow<CheckoutSession?>(null)
    val checkout = _checkout.asStateFlow()
    private val _busy = MutableStateFlow(false)
    val busy = _busy.asStateFlow()

    init { refresh() }

    fun refresh() = viewModelScope.launch { _status.value = repo.status() }

    fun upgrade(tier: String) = viewModelScope.launch {
        _busy.value = true
        _checkout.value = repo.startCheckout(tier)
        _busy.value = false
    }

    fun cancel() = viewModelScope.launch {
        _busy.value = true
        repo.cancel()
        _status.value = repo.status()
        _busy.value = false
    }

    fun clearCheckout() { _checkout.value = null }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PremiumScreen(
    onBack: () -> Unit,
    vm: PremiumViewModel = hiltViewModel(),
) {
    val status by vm.status.collectAsState()
    val checkout by vm.checkout.collectAsState()
    val busy by vm.busy.collectAsState()
    val ctx = LocalContext.current

    LaunchedEffect(checkout) {
        val cs = checkout ?: return@LaunchedEffect
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(cs.url)))
        vm.clearCheckout()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Premium") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier.padding(padding).fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Your plan", style = MaterialTheme.typography.titleMedium)
            val tier = status?.tier ?: "free"
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(tier.replaceFirstChar { it.uppercase() },
                         style = MaterialTheme.typography.headlineSmall,
                         fontWeight = FontWeight.Bold)
                    status?.features?.takeIf { it.isNotEmpty() }?.let {
                        Text("Features: ${it.joinToString(", ")}",
                             style = MaterialTheme.typography.bodySmall,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            if (tier == "free") {
                Button(onClick = { vm.upgrade("plus") }, enabled = !busy,
                       modifier = Modifier.fillMaxWidth()) { Text("Upgrade to Plus") }
                OutlinedButton(onClick = { vm.upgrade("pro") }, enabled = !busy,
                       modifier = Modifier.fillMaxWidth()) { Text("Upgrade to Pro") }
            } else {
                OutlinedButton(onClick = { vm.cancel() }, enabled = !busy,
                       modifier = Modifier.fillMaxWidth()) { Text("Cancel subscription") }
            }
        }
    }
}
