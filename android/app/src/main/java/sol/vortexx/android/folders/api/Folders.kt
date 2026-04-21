package sol.vortexx.android.folders.api

import kotlinx.coroutines.flow.StateFlow

data class ChatFolder(
    val id: String,
    val title: String,
    val roomIds: Set<Long>,
    val isSystem: Boolean = false,
)

interface Folders {
    val folders: StateFlow<List<ChatFolder>>
    val archived: StateFlow<Set<Long>>

    fun create(title: String, roomIds: Set<Long>): ChatFolder
    fun delete(id: String)
    fun rename(id: String, newTitle: String)
    fun setMembers(id: String, roomIds: Set<Long>)

    fun archive(roomId: Long)
    fun unarchive(roomId: Long)
}
