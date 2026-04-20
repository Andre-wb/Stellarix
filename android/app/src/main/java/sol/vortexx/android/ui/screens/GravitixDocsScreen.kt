package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import sol.vortexx.android.i18n.api.LocaleSource
import javax.inject.Inject

/**
 * Minimal Gravitix docs viewer — renders the same content the web client
 * shows, but in Compose. Pulls entries from the active locale bundle
 * under the `gravitixDocs.*` namespace (already shipped in assets/locales).
 */
@HiltViewModel
class GravitixDocsViewModel @Inject constructor(
    private val locales: LocaleSource,
) : ViewModel() {
    var sections: List<Pair<String, String>> by mutableStateOf(emptyList())
        private set

    fun load() {
        viewModelScope.launch {
            // A short curated path list — covers the H1s and first-level
            // body paragraphs. Extending this to every subsection is a
            // matter of adding more keys here; no code changes.
            val paths = listOf(
                "gravitixDocs.title", "gravitixDocs.subtitle",
                "gravitixDocs.intro", "gravitixDocs.introDesc",
                "gravitixDocs.designGoals",
            )
            sections = paths.map { it to locales.translate(it) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GravitixDocsScreen(onBack: () -> Unit, vm: GravitixDocsViewModel = hiltViewModel()) {
    LaunchedEffect(Unit) { vm.load() }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Gravitix docs") },
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
            items(vm.sections) { (key, value) ->
                Column(Modifier.padding(16.dp)) {
                    Text(key, style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(value, style = MaterialTheme.typography.bodyLarge,
                         color = MaterialTheme.colorScheme.onBackground)
                }
            }
        }
    }
}
