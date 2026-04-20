package sol.vortexx.android.bots.impl

import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.Serializable
import sol.vortexx.android.bots.api.BotsRepository
import sol.vortexx.android.db.dao.BotDao
import sol.vortexx.android.db.entities.BotEntity
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpBotsRepository @Inject constructor(
    private val http: VortexHttpClient,
    private val dao: BotDao,
) : BotsRepository {

    override fun marketplace(): Flow<List<BotEntity>> = dao.observeMarketplace()
    override fun installed():   Flow<List<BotEntity>> = dao.observeInstalled()

    override suspend fun refreshMarketplace(): Boolean = runCatching {
        val resp = http.client.get("api/bots/marketplace")
        if (!resp.status.isSuccess()) return@runCatching false
        dao.upsertAll(resp.body<List<BotDto>>().map(BotDto::toEntity))
        true
    }.getOrDefault(false)

    override suspend fun install(id: Long): Boolean = runCatching {
        val resp = http.client.post("api/bots/$id/install")
        if (resp.status.isSuccess()) { dao.setInstalled(id, true); true } else false
    }.getOrDefault(false)

    override suspend fun uninstall(id: Long): Boolean = runCatching {
        val resp = http.client.delete("api/bots/$id/install")
        if (resp.status.isSuccess()) { dao.setInstalled(id, false); true } else false
    }.getOrDefault(false)

    @Serializable private data class BotDto(
        val id: Long, val name: String, val author: String = "",
        val short_description: String = "", val avatar_url: String? = null,
        val installed: Boolean = false, val rating: Double = 0.0,
        val install_count: Long = 0,
    ) {
        fun toEntity() = BotEntity(
            id = id, name = name, author = author,
            shortDescription = short_description, avatarUrl = avatar_url,
            installed = installed, rating = rating, installCount = install_count,
        )
    }
}
