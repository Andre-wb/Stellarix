package sol.vortexx.android.bots.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.BotEntity

interface BotsRepository {
    fun marketplace(): Flow<List<BotEntity>>
    fun installed():   Flow<List<BotEntity>>
    suspend fun refreshMarketplace(): Boolean
    suspend fun install(id: Long): Boolean
    suspend fun uninstall(id: Long): Boolean
}
