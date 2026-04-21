package sol.vortexx.android.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import sol.vortexx.android.chat.api.IncomingMessages
import sol.vortexx.android.chat.api.MessageActions
import sol.vortexx.android.chat.api.MessageSender
import sol.vortexx.android.chat.api.Presence
import sol.vortexx.android.db.entities.MessageEntity
import sol.vortexx.android.files.api.FileTransferService
import sol.vortexx.android.files.api.TransferProgress
import sol.vortexx.android.stickers.api.VoiceRecorder
import sol.vortexx.android.threads.api.ThreadsRepository
import sol.vortexx.android.emoji.api.EmojiCatalog
import sol.vortexx.android.emoji.ui.EmojiPicker
import sol.vortexx.android.ui.components.AttachmentBar
import sol.vortexx.android.ui.components.ReadReceiptsPill
import sol.vortexx.android.ui.components.TypingRow
import sol.vortexx.android.ui.theme.VortexPurple
import javax.inject.Inject
import java.io.ByteArrayInputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Full chat screen. Hosts the bubble list, composer, attachments,
 * typing-indicator, read-receipt pills, and the message context menu
 * (copy / reply / edit / react / delete / open-thread).
 */
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val sender: MessageSender,
    private val incoming: IncomingMessages,
    private val actions: MessageActions,
    private val presence: Presence,
    private val threads: ThreadsRepository,
    private val files: FileTransferService,
    private val auth: sol.vortexx.android.auth.api.AuthRepository,
    val voiceRecorder: VoiceRecorder,
    val emojiCatalog: EmojiCatalog,
) : ViewModel() {

    val selfUsername: kotlinx.coroutines.flow.Flow<String?> = auth.session.map {
        (it as? sol.vortexx.android.auth.api.Session.LoggedIn)?.username
    }

    data class ComposerState(
        val draft: String = "",
        val replyToId: Long? = null,
        val replyToPreview: String? = null,
        val editingId: Long? = null,
    )

    var roomId: Long = 0L
        private set

    private val _composer = MutableStateFlow(ComposerState())
    val composer = _composer.asStateFlow()

    fun bind(roomId: Long) { this.roomId = roomId }

    val messages by lazy {
        incoming.messagesIn(roomId).stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyList(),
        )
    }
    val typing by lazy {
        presence.typingIn(roomId).stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptySet(),
        )
    }
    val reads by lazy {
        presence.readUpTo(roomId).stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyMap(),
        )
    }

    fun onDraftChange(v: String) {
        _composer.value = _composer.value.copy(draft = v)
        if (v.isNotBlank()) viewModelScope.launch { presence.sendTyping(roomId) }
    }

    fun submit() {
        val c = _composer.value
        val text = c.draft.trim()
        if (text.isEmpty()) return
        viewModelScope.launch {
            when {
                c.editingId != null -> actions.edit(c.editingId, text)
                c.replyToId != null -> actions.reply(roomId, c.replyToId, text)
                else                -> sender.send(roomId, text)
            }
            _composer.value = ComposerState()
        }
    }

    fun beginReply(msg: MessageEntity) {
        _composer.value = _composer.value.copy(
            replyToId = msg.id,
            replyToPreview = msg.plaintext?.take(80) ?: "…",
            editingId = null,
        )
    }
    fun beginEdit(msg: MessageEntity) {
        _composer.value = _composer.value.copy(
            editingId = msg.id,
            draft = msg.plaintext ?: "",
            replyToId = null,
            replyToPreview = null,
        )
    }
    fun cancelComposerMode() {
        _composer.value = _composer.value.copy(
            replyToId = null, replyToPreview = null, editingId = null,
        )
    }

    fun react(msg: MessageEntity, emoji: String) { viewModelScope.launch { actions.react(msg.id, emoji) } }
    fun delete(msg: MessageEntity) { viewModelScope.launch { actions.delete(msg.id) } }

    fun openThread(msg: MessageEntity, onReady: (Long) -> Unit) {
        viewModelScope.launch {
            val t = threads.create(roomId, msg.id, msg.plaintext?.take(40) ?: "thread")
            if (t != null) onReady(t.roomId)
        }
    }

    fun markVisible(id: Long) { viewModelScope.launch { presence.markRead(roomId, id) } }

    data class UploadProgress(val percent: Int, val filename: String)

    private val _uploadProgress = MutableStateFlow<UploadProgress?>(null)
    val uploadProgress = _uploadProgress.asStateFlow()

    fun sendVoice(bytes: ByteArray) {
        viewModelScope.launch {
            pipeUpload("voice.ogg", ByteArrayInputStream(bytes), bytes.size.toLong())
        }
    }

    fun sendFile(ctx: Context, uri: android.net.Uri) {
        viewModelScope.launch {
            runCatching {
                val stream = ctx.contentResolver.openInputStream(uri) ?: return@runCatching
                val name = uri.lastPathSegment ?: "file"
                val size = ctx.contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } ?: 0L
                stream.use { s -> pipeUpload(name, s, size) }
            }
        }
    }

    private suspend fun pipeUpload(name: String, s: java.io.InputStream, size: Long) {
        files.upload(roomId, s, name, size).collect { ev ->
            when (ev) {
                is TransferProgress.InFlight -> {
                    val pct = if (size > 0) ((ev.done * 100) / size).toInt().coerceIn(0, 100) else 0
                    _uploadProgress.value = UploadProgress(pct, name)
                }
                is TransferProgress.Done,
                is TransferProgress.Error -> _uploadProgress.value = null
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    roomId: Long,
    onOpenThread: (Long) -> Unit = {},
    onBack: () -> Unit = {},
    vm: ChatViewModel = hiltViewModel(),
) {
    LaunchedEffect(roomId) { vm.bind(roomId) }
    val messages by vm.messages.collectAsState()
    val composer by vm.composer.collectAsState()
    val typing by vm.typing.collectAsState()
    val reads by vm.reads.collectAsState()
    val self by vm.selfUsername.collectAsState(initial = null)
    val upload by vm.uploadProgress.collectAsState()
    val listState = rememberLazyListState()
    val ctx = LocalContext.current
    var deleteTarget by remember { mutableStateOf<MessageEntity?>(null) }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    // Observe the last visible index and mark the message there as read.
    // Snapshot flow gives us a debounced stream so we don't spam the
    // server on every pixel scroll.
    LaunchedEffect(messages) {
        androidx.compose.runtime.snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index }
            .collect { idx ->
                if (idx == null) return@collect
                messages.getOrNull(idx)?.let { vm.markVisible(it.id) }
            }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Room #$roomId") },
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
        Column(Modifier.padding(padding).fillMaxSize()) {
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                items(messages, key = MessageEntity::id) { msg ->
                    Bubble(
                        msg = msg,
                        isOwn = msg.senderUsername == null || msg.senderUsername == self,
                        readThrough = reads,
                        onCopy   = { copyToClipboard(ctx, msg.plaintext ?: "") },
                        onReply  = { vm.beginReply(msg) },
                        onEdit   = { vm.beginEdit(msg) },
                        onReact  = { emoji -> vm.react(msg, emoji) },
                        onDelete = { deleteTarget = msg },
                        onOpenThread = { vm.openThread(msg) { tid -> onOpenThread(tid) } },
                    )
                }
            }

            TypingRow(users = typing)

            upload?.let { up ->
                androidx.compose.material3.LinearProgressIndicator(
                    progress = { up.percent / 100f },
                    modifier = Modifier.fillMaxWidth(),
                    color = VortexPurple,
                )
                Text(
                    "${up.filename} · ${up.percent}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                )
            }

            ComposerBar(
                composer = composer,
                voiceRecorder = vm.voiceRecorder,
                emojiCatalog = vm.emojiCatalog,
                onDraft  = vm::onDraftChange,
                onSubmit = vm::submit,
                onCancelMode = vm::cancelComposerMode,
                onVoice = { bytes -> vm.sendVoice(bytes) },
                onFile  = { uri -> vm.sendFile(ctx, uri) },
            )
        }
    }

    deleteTarget?.let { t ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            title = { Text("Delete message?") },
            text  = { Text("This cannot be undone.") },
            confirmButton = {
                TextButton(onClick = { vm.delete(t); deleteTarget = null }) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { deleteTarget = null }) { Text("Cancel") }
            },
        )
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun Bubble(
    msg: MessageEntity,
    isOwn: Boolean,
    readThrough: Map<Long, Long>,
    onCopy: () -> Unit,
    onReply: () -> Unit,
    onEdit: () -> Unit,
    onReact: (String) -> Unit,
    onDelete: () -> Unit,
    onOpenThread: () -> Unit,
) {
    var menuOpen by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0x120D0D1A))
            .combinedClickable(
                onClick     = { },
                onLongClick = { menuOpen = true },
            )
            .padding(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                msg.senderUsername ?: "—",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.width(8.dp))
            Text(
                SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(msg.sentAt)),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            )
            if (msg.editedAt != null) Text(
                "· edited",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                modifier = Modifier.padding(start = 4.dp),
            )
        }
        if (msg.replyTo != null) Text(
            "↵ replying to #${msg.replyTo}",
            style = MaterialTheme.typography.labelSmall,
            color = VortexPurple,
        )
        Text(
            msg.plaintext ?: "(decrypting…)",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onBackground,
            textDecoration = if (msg.plaintext == null) TextDecoration.Underline else null,
        )

        // Seen-by pill only on outgoing messages — doesn't make sense to
        // tell the user that the author of a remote message "saw" it.
        if (isOwn) ReadReceiptsPill(messageId = msg.id, readThrough = readThrough)

        DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
            DropdownMenuItem(text = { Text("Copy") },        onClick = { onCopy();        menuOpen = false })
            DropdownMenuItem(text = { Text("Reply") },       onClick = { onReply();       menuOpen = false })
            DropdownMenuItem(text = { Text("Edit") },        onClick = { onEdit();        menuOpen = false })
            DropdownMenuItem(text = { Text("Open thread") }, onClick = { onOpenThread();  menuOpen = false })
            DropdownMenuItem(text = { Text("Delete") },      onClick = { onDelete();      menuOpen = false })
            Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                listOf("👍", "❤️", "😂", "🔥", "✅").forEach { emoji ->
                    Text(
                        emoji,
                        style = MaterialTheme.typography.titleLarge,
                        modifier = Modifier
                            .padding(horizontal = 4.dp)
                            .combinedClickable(
                                onClick     = { onReact(emoji); menuOpen = false },
                                onLongClick = {},
                            ),
                    )
                }
            }
        }
    }
}

@Composable
private fun ComposerBar(
    composer: ChatViewModel.ComposerState,
    voiceRecorder: VoiceRecorder,
    emojiCatalog: EmojiCatalog,
    onDraft: (String) -> Unit,
    onSubmit: () -> Unit,
    onCancelMode: () -> Unit,
    onVoice: (ByteArray) -> Unit,
    onFile: (android.net.Uri) -> Unit,
) {
    var emojiOpen by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth()) {
        if (composer.replyToPreview != null || composer.editingId != null) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color(0x22000000))
                    .padding(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        if (composer.editingId != null) "Editing message" else "Reply to",
                        style = MaterialTheme.typography.labelSmall,
                        color = VortexPurple,
                    )
                    Text(
                        composer.replyToPreview ?: "",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                    )
                }
                IconButton(onClick = onCancelMode) {
                    Icon(Icons.Filled.Close, contentDescription = "Cancel")
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            AttachmentBar(
                recorder      = voiceRecorder,
                onVoiceReady  = onVoice,
                onFilePicked  = onFile,
            )
            OutlinedTextField(
                value = composer.draft,
                onValueChange = onDraft,
                modifier = Modifier.weight(1f),
                placeholder = { Text("Message") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            )
            IconButton(
                onClick = { emojiOpen = !emojiOpen },
                modifier = Modifier.semantics {
                    contentDescription = if (emojiOpen) "Hide emoji" else "Show emoji"
                },
            ) { Text("\uD83D\uDE00") }
            IconButton(onClick = onSubmit, enabled = composer.draft.isNotBlank()) {
                Icon(Icons.Filled.Send, contentDescription = "Send", tint = VortexPurple)
            }
        }
        if (emojiOpen) {
            EmojiPicker(catalog = emojiCatalog) { emoji ->
                onDraft(composer.draft + emoji)
            }
        }
    }
}

private fun copyToClipboard(ctx: Context, text: String) {
    val cb = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    cb.setPrimaryClip(ClipData.newPlainText("vortex-message", text))
}
