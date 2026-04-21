package sol.vortexx.android.contacts.impl

import io.ktor.client.call.body
import io.ktor.client.request.*
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.contacts.api.Contact
import sol.vortexx.android.contacts.api.Contacts
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpContacts @Inject constructor(
    private val http: VortexHttpClient,
) : Contacts {
    @Serializable private data class Wrap(val contacts: List<Contact>)
    @Serializable private data class AddBody(val username: String)

    override suspend fun list(): List<Contact> = runCatching {
        val resp = http.client.get("api/contacts")
        if (!resp.status.isSuccess()) emptyList() else resp.body<Wrap>().contacts
    }.getOrDefault(emptyList())

    override suspend fun add(username: String): Contact? = runCatching {
        val resp = http.client.post("api/contacts") {
            contentType(ContentType.Application.Json)
            setBody(AddBody(username))
        }
        if (!resp.status.isSuccess()) null else resp.body<Contact>()
    }.getOrNull()

    override suspend fun remove(id: Long) {
        runCatching { http.client.delete("api/contacts/$id") }
    }

    override suspend fun search(query: String): List<Contact> = runCatching {
        val resp = http.client.get("api/contacts/search") { url { parameters.append("q", query) } }
        if (!resp.status.isSuccess()) emptyList() else resp.body<Wrap>().contacts
    }.getOrDefault(emptyList())
}
