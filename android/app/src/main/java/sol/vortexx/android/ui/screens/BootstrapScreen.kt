package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.bootstrap.api.NodeDirectory
import sol.vortexx.android.bootstrap.api.NodePreferences
import sol.vortexx.android.bootstrap.api.ProbeResult
import sol.vortexx.android.ui.theme.VortexPurple
import javax.inject.Inject

/**
 * Wave 3 bootstrap flow.
 *
 * 1. On first composition the view model probes the primary controller
 *    URL (vortexx.sol). While the probe is in flight we show a spinner.
 * 2. Success ⇒ persist the base URL in [NodePreferences] and move to
 *    [HomeScreen] (done by the caller via [onConnected]).
 * 3. Failure ⇒ render the manual-entry form, `GO` triggers [probe].
 *
 * The ViewModel depends on abstractions only, so tests can wire a fake
 * [NodeDirectory] + in-memory [NodePreferences] without touching Ktor.
 */
@HiltViewModel
class BootstrapViewModel @Inject constructor(
    private val directory: NodeDirectory,
    private val prefs: NodePreferences,
) : ViewModel() {

    sealed interface State {
        data object Probing : State
        data class NeedsUrl(val lastError: String?) : State
        data class Ready(val baseUrl: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Probing)
    val state: StateFlow<State> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val saved = runCatching { prefs.baseUrl.collect { } }  // no-op, just to be polite
            // ↑ won't reach here (collect suspends). We fetch first value below.
        }
        viewModelScope.launch {
            val existing = firstSaved()
            if (existing != null) {
                _state.value = State.Ready(existing)
            } else {
                probePrimary()
            }
        }
    }

    private suspend fun firstSaved(): String? {
        // One-shot read from the Flow. DataStore emits an initial value
        // (null if unset) synchronously on first collect.
        var seen: String? = null
        val job = viewModelScope.launch {
            prefs.baseUrl.collect { seen = it; throw kotlinx.coroutines.CancellationException() }
        }
        job.join()
        return seen
    }

    fun probePrimary() {
        _state.value = State.Probing
        viewModelScope.launch {
            when (val r = directory.probePrimary()) {
                is ProbeResult.Ok -> commit(r.baseUrl)
                is ProbeResult.Unreachable -> _state.value = State.NeedsUrl(r.reason)
            }
        }
    }

    fun probe(url: String) {
        _state.value = State.Probing
        viewModelScope.launch {
            when (val r = directory.probe(url)) {
                is ProbeResult.Ok -> commit(r.baseUrl)
                is ProbeResult.Unreachable -> _state.value = State.NeedsUrl(r.reason)
            }
        }
    }

    private suspend fun commit(url: String) {
        prefs.setBaseUrl(url)
        _state.value = State.Ready(url)
    }
}

@Composable
fun BootstrapScreen(
    onConnected: (String) -> Unit,
    vm: BootstrapViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .clip(CircleShape)
                    .background(VortexPurple),
            )
            Text(
                text = "VORTEX",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.padding(top = 14.dp),
            )

            when (val s = state) {
                is BootstrapViewModel.State.Probing -> {
                    CircularProgressIndicator(
                        color = VortexPurple,
                        modifier = Modifier.padding(top = 24.dp),
                    )
                    Text(
                        text = "connecting to vortexx.sol…",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 12.dp),
                    )
                }

                is BootstrapViewModel.State.NeedsUrl -> ManualUrlForm(
                    lastError = s.lastError,
                    onProbe   = vm::probe,
                    onRetry   = vm::probePrimary,
                )

                is BootstrapViewModel.State.Ready -> {
                    // Hand control up; the activity swaps to HomeScreen.
                    onConnected(s.baseUrl)
                }
            }
        }
    }
}

@Composable
private fun ManualUrlForm(
    lastError: String?,
    onProbe: (String) -> Unit,
    onRetry: () -> Unit,
) {
    var input by remember { mutableStateOf("") }

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.padding(top = 24.dp).fillMaxWidth(),
    ) {
        Text(
            text = "Can't reach vortexx.sol." +
                (lastError?.let { "\n($it)" } ?: ""),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(
            value = input,
            onValueChange = { input = it },
            singleLine = true,
            label = { Text("Mirror or node URL") },
            placeholder = { Text("https://mirror.example.com") },
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
        )
        Button(
            onClick = { onProbe(input) },
            colors = ButtonDefaults.buttonColors(containerColor = VortexPurple),
            enabled = input.isNotBlank(),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        ) { Text("Connect") }
        TextButton(
            onClick = onRetry,
            modifier = Modifier.padding(top = 8.dp),
        ) { Text("Retry vortexx.sol") }
    }
}
