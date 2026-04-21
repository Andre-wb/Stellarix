package sol.vortexx.android.contacts.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.contacts.api.Contact
import sol.vortexx.android.contacts.api.Contacts
import javax.inject.Inject

@HiltViewModel
class ContactsViewModel @Inject constructor(
    private val repo: Contacts,
) : ViewModel() {
    private val _contacts = MutableStateFlow<List<Contact>>(emptyList())
    val contacts = _contacts.asStateFlow()
    private val _query = MutableStateFlow("")
    val query = _query.asStateFlow()
    private val _results = MutableStateFlow<List<Contact>>(emptyList())
    val results = _results.asStateFlow()

    init { refresh() }

    fun refresh() = viewModelScope.launch { _contacts.value = repo.list() }

    fun setQuery(q: String) {
        _query.value = q
        if (q.isBlank()) { _results.value = emptyList(); return }
        viewModelScope.launch { _results.value = repo.search(q) }
    }

    fun addByUsername(username: String) = viewModelScope.launch {
        val added = repo.add(username.trim()) ?: return@launch
        _contacts.value = _contacts.value + added
    }

    fun remove(id: Long) = viewModelScope.launch {
        repo.remove(id); _contacts.value = _contacts.value.filterNot { it.id == id }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ContactsScreen(
    onBack: () -> Unit,
    onOpenDm: (Long) -> Unit = {},
    vm: ContactsViewModel = hiltViewModel(),
) {
    val contacts by vm.contacts.collectAsState()
    val query by vm.query.collectAsState()
    val results by vm.results.collectAsState()
    var showAdd by remember { mutableStateOf(false) }
    var addUsername by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Contacts") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                actions = {
                    IconButton(onClick = { showAdd = true }) {
                        Icon(Icons.Filled.PersonAdd, contentDescription = "Add contact")
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            OutlinedTextField(
                value = query, onValueChange = vm::setQuery,
                placeholder = { Text("Search") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(12.dp),
            )
            val visible = if (query.isBlank()) contacts else results
            if (visible.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No contacts", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                LazyColumn {
                    items(visible, key = Contact::id) { c ->
                        ContactRow(c,
                            onClick = { onOpenDm(c.id) },
                            onDelete = { vm.remove(c.id) },
                        )
                    }
                }
            }
        }
    }

    if (showAdd) AlertDialog(
        onDismissRequest = { showAdd = false; addUsername = "" },
        confirmButton = {
            TextButton(
                onClick = { vm.addByUsername(addUsername); showAdd = false; addUsername = "" },
                enabled = addUsername.isNotBlank(),
            ) { Text("Add") }
        },
        dismissButton = {
            TextButton(onClick = { showAdd = false; addUsername = "" }) { Text("Cancel") }
        },
        title = { Text("Add contact") },
        text = {
            OutlinedTextField(
                value = addUsername, onValueChange = { addUsername = it },
                placeholder = { Text("username or +phone") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        },
    )
}

@Composable
private fun ContactRow(c: Contact, onClick: () -> Unit, onDelete: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(36.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center,
        ) { Text(c.username.firstOrNull()?.uppercase() ?: "?") }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(c.display_name ?: c.username, fontWeight = FontWeight.SemiBold)
            Text("@${c.username}", style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        IconButton(onClick = onDelete) {
            Icon(Icons.Filled.Delete, contentDescription = "Remove", tint = MaterialTheme.colorScheme.error)
        }
    }
}
