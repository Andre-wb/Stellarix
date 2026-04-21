package sol.vortexx.android.reactions.api

data class Reaction(
    val messageId: Long,
    val emoji: String,
    val count: Int,
    val reactedByMe: Boolean,
)

interface Reactions {
    fun reactionsFor(messageId: Long): List<Reaction>
    fun apply(messageId: Long, emoji: String, delta: Int, byMe: Boolean)
}
