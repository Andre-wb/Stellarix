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
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import sol.vortexx.android.db.entities.ThreadEntity
import sol.vortexx.android.threads.api.ThreadsRepository
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class ThreadsViewModel @Inject constructor(
    private val repo: ThreadsRepository,
) : ViewModel() {

    private val _roomId = MutableStateFlow<Long?>(null)

    val threads = _roomId
        .flatMapLatest { id -> if (id == null) kotlinx.coroutines.flow.flowOf(emptyList()) else repo.observeForRoom(id) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun bind(roomId: Long) {
        _roomId.value = roomId
        viewModelScope.launch { repo.refresh(roomId) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ThreadsScreen(
    roomId: Long,
    onThreadClick: (Long) -> Unit,
    onBack: () -> Unit,
    vm: ThreadsViewModel = hiltViewModel(),
) {
    LaunchedEffect(roomId) { vm.bind(roomId) }
    val items by vm.threads.collectAsState()

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Threads") },
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
            items(items, key = ThreadEntity::id) { t ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clickable { onThreadClick(t.id) }
                        .padding(16.dp),
                ) {
                    Text(t.title,
                         fontWeight = FontWeight.SemiBold,
                         color = MaterialTheme.colorScheme.onBackground)
                    Text("${t.replyCount} replies",
                         style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
