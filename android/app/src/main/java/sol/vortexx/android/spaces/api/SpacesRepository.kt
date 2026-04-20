package sol.vortexx.android.spaces.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.SpaceEntity

interface SpacesRepository {
    fun observe(): Flow<List<SpaceEntity>>
    suspend fun refresh(): Boolean
    suspend fun create(name: String, isPublic: Boolean): SpaceEntity?
    suspend fun leave(id: Long): Boolean
}
