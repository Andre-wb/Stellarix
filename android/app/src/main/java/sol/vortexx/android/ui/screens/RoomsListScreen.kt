package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Badge
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import sol.vortexx.android.db.entities.RoomEntity
import sol.vortexx.android.rooms.api.RoomResult
import sol.vortexx.android.rooms.api.RoomsRepository
import sol.vortexx.android.ui.theme.VortexPurple
import javax.inject.Inject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Rooms list = primary post-auth screen. Mirrors the web sidebar:
 * last-message-descending sort, unread badge, avatar emoji, invite/create
 * entrypoints from the top-right. Tapping a row navigates into [ChatScreen].
 */
@HiltViewModel
class RoomsListViewModel @Inject constructor(
    private val repo: RoomsRepository,
) : ViewModel() {

    sealed interface ActionState {
        data object Idle : ActionState
        data object Busy : ActionState
        data class Error(val reason: String) : ActionState
    }

    val rooms = repo.observe().stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = emptyList(),
    )

    private val _refreshState = kotlinx.coroutines.flow.MutableStateFlow(false)
    val refreshing = _refreshState

    private val _action = kotlinx.coroutines.flow.MutableStateFlow<ActionState>(ActionState.Idle)
    val action = _action

    init { refresh() }

    fun refresh() {
        _refreshState.value = true
        viewModelScope.launch {
            repo.refresh()
            _refreshState.value = false
        }
    }

    fun createRoom(name: String, isPrivate: Boolean, onCreated: (Long) -> Unit) {
        _action.value = ActionState.Busy
        viewModelScope.launch {
            when (val r = repo.create(name.trim(), isPrivate)) {
                is RoomResult.Ok -> { _action.value = ActionState.Idle; onCreated(r.roomId) }
                is RoomResult.Error -> _action.value = ActionState.Error(r.message.ifBlank { r.code })
            }
        }
    }

    fun joinByInvite(code: String, onJoined: (Long) -> Unit) {
        _action.value = ActionState.Busy
        viewModelScope.launch {
            when (val r = repo.joinByInvite(code.trim())) {
                is RoomResult.Ok -> { _action.value = ActionState.Idle; onJoined(r.roomId) }
                is RoomResult.Error -> _action.value = ActionState.Error(r.message.ifBlank { r.code })
            }
        }
    }

    fun dismissError() { _action.value = ActionState.Idle }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RoomsListScreen(
    onRoomClick: (Long) -> Unit,
    onSettingsClick: () -> Unit,
    onOpenSpaces: () -> Unit = {},
    onOpenBots: () -> Unit = {},
    onOpenSearch: () -> Unit = {},
    onOpenDocs: () -> Unit = {},
    vm: RoomsListViewModel = hiltViewModel(),
) {
    val rooms by vm.rooms.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val action by vm.action.collectAsState()

    var showCreate by remember { mutableStateOf(false) }
    var showJoin by remember { mutableStateOf(false) }
    val drawerState = androidx.compose.material3.rememberDrawerState(androidx.compose.material3.DrawerValue.Closed)
    val scope = androidx.compose.runtime.rememberCoroutineScope()

    androidx.compose.material3.ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            androidx.compose.material3.ModalDrawerSheet {
                androidx.compose.foundation.layout.Column(
                    modifier = Modifier.padding(16.dp),
                ) {
                    Text("Vortex", style = MaterialTheme.typography.titleLarge,
                         color = MaterialTheme.colorScheme.onBackground)
                    androidx.compose.foundation.layout.Spacer(Modifier.height(20.dp))
                    DrawerLink("Spaces")   { scope.launch { drawerState.close() }; onOpenSpaces() }
                    DrawerLink("Bots")     { scope.launch { drawerState.close() }; onOpenBots() }
                    DrawerLink("Search")   { scope.launch { drawerState.close() }; onOpenSearch() }
                    DrawerLink("Gravitix docs") { scope.launch { drawerState.close() }; onOpenDocs() }
                    androidx.compose.material3.HorizontalDivider(Modifier.padding(vertical = 12.dp))
                    DrawerLink("Settings") { scope.launch { drawerState.close() }; onSettingsClick() }
                }
            }
        },
    ) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier.size(8.dp).clip(CircleShape).background(VortexPurple),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text("VORTEX", fontWeight = FontWeight.Bold,
                             color = MaterialTheme.colorScheme.onBackground)
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { scope.launch { drawerState.open() } }) {
                        Icon(Icons.Filled.Menu, contentDescription = "Menu",
                             tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                },
                actions = {
                    IconButton(onClick = { vm.refresh() }) {
                        if (refreshing) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Filled.Refresh, contentDescription = "Refresh",
                                  tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    IconButton(onClick = onOpenSearch) {
                        Icon(Icons.Filled.Search, contentDescription = "Search",
                             tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { showCreate = true },
                containerColor = VortexPurple,
            ) { Icon(Icons.Filled.Add, contentDescription = "New room") }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            if (rooms.isEmpty() && !refreshing) EmptyState(
                onCreate = { showCreate = true },
                onJoin   = { showJoin = true },
            ) else LazyColumn(Modifier.fillMaxSize()) {
                items(rooms, key = RoomEntity::id) { room ->
                    RoomRow(room, onClick = { onRoomClick(room.id) })
                }
            }
        }
    }

    if (showCreate) CreateRoomDialog(
        busy = action is RoomsListViewModel.ActionState.Busy,
        onDismiss = { showCreate = false; vm.dismissError() },
        onSwitchToJoin = { showCreate = false; showJoin = true },
        onCreate = { name, isPrivate ->
            vm.createRoom(name, isPrivate) { id -> showCreate = false; onRoomClick(id) }
        },
    )

    if (showJoin) JoinRoomDialog(
        busy = action is RoomsListViewModel.ActionState.Busy,
        onDismiss = { showJoin = false; vm.dismissError() },
        onJoin = { code ->
            vm.joinByInvite(code) { id -> showJoin = false; onRoomClick(id) }
        },
    )

    (action as? RoomsListViewModel.ActionState.Error)?.let {
        AlertDialog(
            onDismissRequest = vm::dismissError,
            title = { Text("Error") },
            text  = { Text(it.reason) },
            confirmButton = { TextButton(onClick = vm::dismissError) { Text("OK") } },
        )
    }
    } // ModalNavigationDrawer
}

@Composable
private fun DrawerLink(label: String, onClick: () -> Unit) {
    Text(
        text = label,
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onBackground,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp),
    )
}

@Composable
private fun RoomRow(room: RoomEntity, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(44.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center,
        ) { Text(room.avatarEmoji, style = MaterialTheme.typography.titleLarge) }

        Spacer(Modifier.width(12.dp))

        Column(Modifier.weight(1f)) {
            Text(
                room.name,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onBackground,
            )
            Text(
                text = buildString {
                    if (room.isChannel) append("channel • ")
                    else if (room.isDm)  append("dm • ")
                    append("${room.memberCount} members")
                    room.lastMessageAt?.let {
                        append(" • ")
                        append(SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(it)))
                    }
                },
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (room.unreadCount > 0) Badge(
            containerColor = VortexPurple,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ) { Text(room.unreadCount.toString()) }
    }
}

@Composable
private fun EmptyState(onCreate: () -> Unit, onJoin: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("No rooms yet", style = MaterialTheme.typography.titleLarge,
             color = MaterialTheme.colorScheme.onBackground)
        Text("Create one, or join with an invite code.",
             style = MaterialTheme.typography.bodyMedium,
             color = MaterialTheme.colorScheme.onSurfaceVariant,
             modifier = Modifier.padding(top = 8.dp))
        Spacer(Modifier.height(20.dp))
        Button(onClick = onCreate, colors = ButtonDefaults.buttonColors(containerColor = VortexPurple)) {
            Text("New room")
        }
        TextButton(onClick = onJoin, modifier = Modifier.padding(top = 8.dp)) {
            Text("Join by invite")
        }
    }
}

@Composable
private fun CreateRoomDialog(
    busy: Boolean,
    onDismiss: () -> Unit,
    onSwitchToJoin: () -> Unit,
    onCreate: (String, Boolean) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var isPrivate by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New room") },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Room name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(
                    modifier = Modifier.padding(top = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = isPrivate, onCheckedChange = { isPrivate = it })
                    Text("Private",
                         style = MaterialTheme.typography.bodyMedium,
                         modifier = Modifier.padding(start = 8.dp))
                }
                TextButton(onClick = onSwitchToJoin) {
                    Text("Have an invite code? Join an existing room")
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onCreate(name, isPrivate) },
                enabled = name.isNotBlank() && !busy,
                colors = ButtonDefaults.buttonColors(containerColor = VortexPurple),
            ) { Text(if (busy) "…" else "Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun JoinRoomDialog(busy: Boolean, onDismiss: () -> Unit, onJoin: (String) -> Unit) {
    var code by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Join room") },
        text = {
            OutlinedTextField(
                value = code,
                onValueChange = { code = it.trim() },
                label = { Text("Invite code") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            Button(
                onClick = { onJoin(code) },
                enabled = code.isNotBlank() && !busy,
                colors = ButtonDefaults.buttonColors(containerColor = VortexPurple),
            ) { Text(if (busy) "…" else "Join") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
