package sol.vortexx.android.emoji.impl

import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import sol.vortexx.android.emoji.api.EmojiCatalog
import sol.vortexx.android.emoji.api.EmojiCategory
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AssetEmojiCatalog @Inject constructor(
    @ApplicationContext context: Context,
) : EmojiCatalog {
    private val prefs: SharedPreferences = context.getSharedPreferences("vortex.emoji", Context.MODE_PRIVATE)
    private val recentsKey = "recent"
    private val cap = 30
    private val data: Map<EmojiCategory, List<String>>
    private val index: List<String>
    private val _recent = MutableStateFlow(readRecent())
    override val recentFlow = _recent.asStateFlow()

    init {
        val raw = context.assets.open("emoji.json").bufferedReader().use { it.readText() }
        val obj = Json.parseToJsonElement(raw).jsonObject
        val mutable = mutableMapOf<EmojiCategory, List<String>>()
        for (cat in EmojiCategory.values().filter { it != EmojiCategory.RECENT }) {
            val arr = obj[cat.slug]?.jsonArray ?: continue
            mutable[cat] = arr.map { it.jsonPrimitive.content }
        }
        data = mutable
        index = mutable.values.flatten()
    }

    override fun categories() = EmojiCategory.values().toList()

    override fun emojis(category: EmojiCategory): List<String> =
        if (category == EmojiCategory.RECENT) readRecent() else data[category].orEmpty()

    override fun search(query: String): List<String> {
        val q = query.trim()
        return if (q.isEmpty()) index else index.filter { it.contains(q) }
    }

    override fun recent(): List<String> = readRecent()

    override fun bumpRecent(emoji: String) {
        val list = readRecent().toMutableList()
        list.remove(emoji)
        list.add(0, emoji)
        val capped = list.take(cap)
        prefs.edit().putString(recentsKey, capped.joinToString("\n")).apply()
        _recent.value = capped
    }

    private fun readRecent(): List<String> =
        prefs.getString(recentsKey, null)?.split("\n")?.filter { it.isNotEmpty() } ?: emptyList()
}
