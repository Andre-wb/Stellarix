package sol.vortexx.android.emoji.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import sol.vortexx.android.emoji.api.EmojiCatalog
import sol.vortexx.android.emoji.api.EmojiCategory

/**
 * Compact bottom-sheet emoji picker. Matches the SwiftUI counterpart:
 * category tabs → search field → 8-column grid.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EmojiPicker(
    catalog: EmojiCatalog,
    onPick: (String) -> Unit,
) {
    var category by remember { mutableStateOf(EmojiCategory.SMILEYS) }
    var query by remember { mutableStateOf("") }
    val recent by catalog.recentFlow.collectAsState()
    val visible = remember(category, query, recent) {
        if (query.isNotBlank()) catalog.search(query) else catalog.emojis(category)
    }

    Column(Modifier.fillMaxWidth().background(Color(0xFF0F0F17)).padding(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            catalog.categories().forEach { cat ->
                Box(
                    Modifier
                        .background(
                            if (cat == category) Color.White.copy(alpha = 0.12f) else Color.Transparent,
                            RoundedCornerShape(6.dp),
                        )
                        .clickable { category = cat; query = "" }
                        .padding(6.dp)
                        .semantics { contentDescription = "emoji.category.${cat.slug}" },
                ) { Text(cat.tabIcon) }
            }
        }
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            placeholder = { Text("search") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().semantics { contentDescription = "emoji.search" },
        )
        Spacer(Modifier.height(6.dp))
        LazyVerticalGrid(
            columns = GridCells.Fixed(8),
            modifier = Modifier.heightIn(min = 200.dp, max = 320.dp),
            contentPadding = PaddingValues(6.dp),
        ) {
            items(visible) { e ->
                Box(
                    Modifier
                        .padding(2.dp)
                        .clickable {
                            catalog.bumpRecent(e)
                            onPick(e)
                        }
                        .semantics { contentDescription = e },
                    contentAlignment = androidx.compose.ui.Alignment.Center,
                ) { Text(e) }
            }
        }
    }
}
