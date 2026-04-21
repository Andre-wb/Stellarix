package sol.vortexx.android.folders.impl

import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import sol.vortexx.android.folders.api.ChatFolder
import sol.vortexx.android.folders.api.Folders
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PrefsFolders @Inject constructor(
    @ApplicationContext ctx: Context,
) : Folders {
    private val prefs: SharedPreferences = ctx.getSharedPreferences("vortex.folders", Context.MODE_PRIVATE)
    private val foldersKey = "list"
    private val archivedKey = "archived"

    @Serializable private data class Stored(val id: String, val title: String, val roomIds: List<Long>)

    private val _folders = MutableStateFlow(buildList())
    override val folders = _folders.asStateFlow()
    private val _archived = MutableStateFlow(readArchived())
    override val archived = _archived.asStateFlow()

    private fun readStored(): List<Stored> {
        val raw = prefs.getString(foldersKey, null) ?: return emptyList()
        return runCatching { Json.decodeFromString<List<Stored>>(raw) }.getOrDefault(emptyList())
    }

    private fun writeStored(list: List<Stored>) {
        prefs.edit().putString(foldersKey, Json.encodeToString(list)).apply()
        _folders.value = buildList()
    }

    private fun readArchived(): Set<Long> =
        prefs.getString(archivedKey, null)?.split(",")?.mapNotNull { it.toLongOrNull() }?.toSet() ?: emptySet()

    private fun writeArchived(set: Set<Long>) {
        prefs.edit().putString(archivedKey, set.joinToString(",")).apply()
        _archived.value = set
    }

    private fun buildList(): List<ChatFolder> {
        val arch = _archived.value
        val all = ChatFolder("all", "All", emptySet(), isSystem = true)
        val archived = ChatFolder("archived", "Archived", arch, isSystem = true)
        val custom = readStored().map { ChatFolder(it.id, it.title, it.roomIds.toSet()) }
        return listOf(all, archived) + custom
    }

    override fun create(title: String, roomIds: Set<Long>): ChatFolder {
        val id = "f-${System.currentTimeMillis()}"
        val list = readStored().toMutableList()
        list += Stored(id, title, roomIds.toList())
        writeStored(list)
        return ChatFolder(id, title, roomIds)
    }

    override fun delete(id: String) = writeStored(readStored().filterNot { it.id == id })
    override fun rename(id: String, newTitle: String) = writeStored(readStored().map {
        if (it.id == id) it.copy(title = newTitle) else it
    })
    override fun setMembers(id: String, roomIds: Set<Long>) = writeStored(readStored().map {
        if (it.id == id) it.copy(roomIds = roomIds.toList()) else it
    })
    override fun archive(roomId: Long) { writeArchived(_archived.value + roomId); _folders.value = buildList() }
    override fun unarchive(roomId: Long) { writeArchived(_archived.value - roomId); _folders.value = buildList() }
}
