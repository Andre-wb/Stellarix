package sol.vortexx.android.stickers.api

import kotlinx.coroutines.flow.Flow

/** Wave 16: sticker packs + saved GIFs + voice notes. */
interface StickerCatalog {
    fun favoritePacks(): Flow<List<StickerPack>>
    suspend fun addPack(packId: String): Boolean
    suspend fun removePack(packId: String): Boolean
}

data class StickerPack(
    val id: String,
    val name: String,
    val coverUrl: String,
    val stickerCount: Int,
)

interface VoiceRecorder {
    suspend fun start(): VoiceSession
}

interface VoiceSession {
    suspend fun stop(): ByteArray              // Opus-in-Ogg
    suspend fun cancel()
}
