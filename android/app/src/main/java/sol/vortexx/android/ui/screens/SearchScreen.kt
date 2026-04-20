package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.db.entities.MessageEntity
import sol.vortexx.android.search.api.SearchRepository
import javax.inject.Inject

@HiltViewModel
class SearchViewModel @Inject constructor(
    private val repo: SearchRepository,
) : ViewModel() {
    private val _results = MutableStateFlow<List<MessageEntity>>(emptyList())
    val results = _results.asStateFlow()

    private var searchJob: Job? = null

    fun onQuery(q: String) {
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            delay(180)          // tiny debounce
            _results.value = repo.search(q)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen(
    onResultClick: (roomId: Long, messageId: Long) -> Unit,
    onBack: () -> Unit,
    vm: SearchViewModel = hiltViewModel(),
) {
    val results by vm.results.collectAsState()
    var query by remember { mutableStateOf("") }
    LaunchedEffect(query) { vm.onQuery(query) }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Search") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                singleLine = true,
                label = { Text("Find a message") },
            )
            LazyColumn(Modifier.fillMaxSize()) {
                items(results, key = MessageEntity::id) { m ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .clickable { onResultClick(m.roomId, m.id) }
                            .padding(12.dp),
                    ) {
                        Text(m.senderUsername ?: "—",
                             style = MaterialTheme.typography.labelSmall,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(m.plaintext ?: "",
                             style = MaterialTheme.typography.bodyMedium,
                             color = MaterialTheme.colorScheme.onBackground,
                             maxLines = 2)
                    }
                }
            }
        }
    }
}
