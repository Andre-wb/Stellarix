package sol.vortexx.android.savedgifs.api

import kotlinx.serialization.Serializable

@Serializable
data class SavedGif(
    val id: Long,
    val url: String,
    val width: Int,
    val height: Int,
    val added_at: Long,
)

interface SavedGifs {
    suspend fun list(): List<SavedGif>
    suspend fun add(url: String, width: Int, height: Int): SavedGif?
    suspend fun remove(id: Long)
}
