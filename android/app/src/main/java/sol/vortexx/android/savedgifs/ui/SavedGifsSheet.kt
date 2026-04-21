package sol.vortexx.android.savedgifs.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.savedgifs.api.SavedGif
import sol.vortexx.android.savedgifs.api.SavedGifs
import javax.inject.Inject

/**
 * Bottom sheet that lists the user's saved GIFs. Tapping a tile calls
 * [onPick] with its URL; long-press opens a delete action. "Add GIF"
 * field takes a URL (no Tenor — personal collection only).
 */
@HiltViewModel
class SavedGifsViewModel @Inject constructor(
    private val repo: SavedGifs,
) : ViewModel() {
    private val _gifs = MutableStateFlow<List<SavedGif>>(emptyList())
    val gifs = _gifs.asStateFlow()
    private val _adding = MutableStateFlow(false)
    val adding = _adding.asStateFlow()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch { _gifs.value = repo.list() }
    }

    fun addFromUrl(url: String) {
        if (url.isBlank()) return
        viewModelScope.launch {
            _adding.value = true
            val added = repo.add(url.trim(), 0, 0)
            if (added != null) _gifs.value = _gifs.value + added
            _adding.value = false
        }
    }

    fun remove(id: Long) {
        viewModelScope.launch {
            repo.remove(id)
            _gifs.value = _gifs.value.filterNot { it.id == id }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SavedGifsSheet(
    onPick: (String) -> Unit,
    onDismiss: () -> Unit,
    vm: SavedGifsViewModel = hiltViewModel(),
) {
    val gifs by vm.gifs.collectAsState()
    val adding by vm.adding.collectAsState()
    var urlInput by remember { mutableStateOf("") }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .background(Color(0xFF0F0F17))
                .padding(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Saved GIFs", style = MaterialTheme.typography.titleMedium,
                     color = MaterialTheme.colorScheme.onBackground, modifier = Modifier.weight(1f))
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Filled.Close, contentDescription = "Close")
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 6.dp)) {
                OutlinedTextField(
                    value = urlInput, onValueChange = { urlInput = it },
                    placeholder = { Text("Paste a .gif URL") },
                    singleLine = true,
                    modifier = Modifier.weight(1f).semantics { contentDescription = "gif.url" },
                )
                Spacer(Modifier.width(6.dp))
                Button(
                    onClick = { vm.addFromUrl(urlInput); urlInput = "" },
                    enabled = urlInput.isNotBlank() && !adding,
                ) { Text("Add") }
            }
            if (gifs.isEmpty()) {
                Text("No saved GIFs yet.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                     modifier = Modifier.padding(16.dp))
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(3),
                    modifier = Modifier.heightIn(min = 200.dp, max = 420.dp),
                    contentPadding = PaddingValues(6.dp),
                ) {
                    items(gifs, key = SavedGif::id) { g ->
                        Box(
                            Modifier
                                .padding(3.dp)
                                .clip(RoundedCornerShape(6.dp))
                                .background(Color.White.copy(alpha = 0.04f))
                                .clickable { onPick(g.url); onDismiss() }
                                .semantics { contentDescription = "gif.${g.id}" },
                        ) {
                            // Image renderer is not pulled in yet — the
                            // tile shows a GIF-glyph placeholder with the
                            // URL stem. Swap for `AsyncImage` once Coil
                            // lands in the build graph.
                            Column(
                                Modifier.fillMaxWidth().heightIn(min = 72.dp, max = 120.dp)
                                    .padding(8.dp),
                                verticalArrangement = Arrangement.Center,
                                horizontalAlignment = Alignment.CenterHorizontally,
                            ) {
                                Text("\uD83C\uDFAC", style = MaterialTheme.typography.titleLarge)
                                Text(
                                    g.url.substringAfterLast('/').take(18),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    maxLines = 1,
                                )
                            }
                            IconButton(
                                onClick = { vm.remove(g.id) },
                                modifier = Modifier.align(Alignment.TopEnd),
                            ) { Icon(Icons.Filled.Close, contentDescription = "Remove") }
                        }
                    }
                }
            }
        }
    }
}
