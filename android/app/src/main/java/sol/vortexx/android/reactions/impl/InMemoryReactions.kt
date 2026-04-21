package sol.vortexx.android.reactions.impl

import sol.vortexx.android.reactions.api.Reaction
import sol.vortexx.android.reactions.api.Reactions
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class InMemoryReactions @Inject constructor() : Reactions {
    private val counts = ConcurrentHashMap<Long, MutableMap<String, Int>>()
    private val mine = ConcurrentHashMap<Long, MutableSet<String>>()

    override fun reactionsFor(messageId: Long): List<Reaction> {
        val c = counts[messageId] ?: return emptyList()
        val m = mine[messageId] ?: emptySet()
        return c.map { (emoji, n) -> Reaction(messageId, emoji, n, emoji in m) }
            .sortedByDescending { it.count }
    }

    @Synchronized
    override fun apply(messageId: Long, emoji: String, delta: Int, byMe: Boolean) {
        val c = counts.getOrPut(messageId) { mutableMapOf() }
        val next = (c[emoji] ?: 0) + delta
        if (next <= 0) c.remove(emoji) else c[emoji] = next
        if (byMe) {
            val m = mine.getOrPut(messageId) { mutableSetOf() }
            if (delta > 0) m.add(emoji) else m.remove(emoji)
        }
    }
}
