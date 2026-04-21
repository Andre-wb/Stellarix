package sol.vortexx.android.emoji.api

import kotlinx.coroutines.flow.StateFlow

enum class EmojiCategory(val slug: String, val tabIcon: String) {
    RECENT("recent", "\uD83D\uDD51"),
    SMILEYS("smileys", "\uD83D\uDE00"),
    PEOPLE("people", "\uD83D\uDC4B"),
    ANIMALS("animals", "\uD83D\uDC36"),
    FOOD("food", "\uD83C\uDF4E"),
    TRAVEL("travel", "\uD83D\uDE97"),
    ACTIVITIES("activities", "\u26BD"),
    OBJECTS("objects", "\uD83D\uDCA1"),
    SYMBOLS("symbols", "\u2764\uFE0F"),
    FLAGS("flags", "\uD83C\uDFC1"),
}

/**
 * Reads the bundled `emoji.json` and maintains an MRU recents ring in
 * SharedPreferences. Matches [io.vortex.ios] semantics 1:1.
 */
interface EmojiCatalog {
    fun categories(): List<EmojiCategory>
    fun emojis(category: EmojiCategory): List<String>
    fun search(query: String): List<String>
    fun recent(): List<String>
    fun bumpRecent(emoji: String)
    val recentFlow: StateFlow<List<String>>
}
