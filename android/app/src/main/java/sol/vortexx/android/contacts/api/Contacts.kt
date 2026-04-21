package sol.vortexx.android.contacts.api

import kotlinx.serialization.Serializable

@Serializable
data class Contact(
    val id: Long,
    val username: String,
    val display_name: String? = null,
    val avatar_url: String? = null,
    val added_at: Long = 0,
)

interface Contacts {
    suspend fun list(): List<Contact>
    suspend fun add(username: String): Contact?
    suspend fun remove(id: Long)
    suspend fun search(query: String): List<Contact>
}
