package sol.vortexx.android.rooms.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.RoomEntity

/** Feature contract for the rooms list / create / join. */
interface RoomsRepository {
    fun observe(): Flow<List<RoomEntity>>
    suspend fun refresh(): RefreshResult
    suspend fun create(name: String, isPrivate: Boolean): RoomResult
    suspend fun joinByInvite(inviteCode: String): RoomResult
    suspend fun leave(roomId: Long): Boolean
}

sealed interface RefreshResult {
    data class Ok(val count: Int) : RefreshResult
    data class Error(val reason: String) : RefreshResult
}

sealed interface RoomResult {
    data class Ok(val roomId: Long) : RoomResult
    data class Error(val code: String, val message: String) : RoomResult
}
