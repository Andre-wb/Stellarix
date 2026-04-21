package sol.vortexx.android.accounts.impl

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import dagger.hilt.android.qualifiers.ApplicationContext
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import sol.vortexx.android.accounts.api.Accounts
import sol.vortexx.android.accounts.api.AccountsError
import sol.vortexx.android.accounts.api.SavedAccount
import sol.vortexx.android.auth.api.SecureStore
import sol.vortexx.android.crypto.api.Signer
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Multi-account switching via X25519-backed challenge-response.
 * Mirrors the web flow (auth.js → switchAccount) and the iOS
 * [KeychainAccountsManager].
 */
@Singleton
class VortexAccounts @Inject constructor(
    @ApplicationContext ctx: Context,
    private val store: SecureStore,
    private val signer: Signer,
    private val http: VortexHttpClient,
) : Accounts {
    private val prefs: SharedPreferences = ctx.getSharedPreferences("vortex.accounts", Context.MODE_PRIVATE)
    private val listKey = "list"
    private val activeKey = "active"
    private val mutex = Mutex()

    private val _list = MutableStateFlow(readList())
    override val list = _list.asStateFlow()
    private val _active = MutableStateFlow(readActive())
    override val active = _active.asStateFlow()

    private fun readList(): List<SavedAccount> =
        runCatching { Json.decodeFromString<List<SavedAccount>>(prefs.getString(listKey, "[]") ?: "[]") }
            .getOrDefault(emptyList())

    private fun writeList(list: List<SavedAccount>) {
        prefs.edit().putString(listKey, Json.encodeToString(list)).apply()
        _list.value = list
    }

    private fun readActive(): SavedAccount? {
        val id = prefs.getString(activeKey, null) ?: return null
        return readList().firstOrNull { it.id == id }
    }

    override suspend fun add(account: SavedAccount, jwt: String, staticKeySeedB64: String) = mutex.withLock {
        val list = readList().filterNot { it.id == account.id } + account
        writeList(list)
        store.putString("account.${account.id}.jwt", jwt)
        store.putString("account.${account.id}.x25519", staticKeySeedB64)
        if (prefs.getString(activeKey, null) == null) {
            prefs.edit().putString(activeKey, account.id).apply()
            _active.value = account
        }
    }

    override suspend fun remove(id: String) = mutex.withLock {
        val list = readList().filterNot { it.id == id }
        writeList(list)
        store.putString("account.$id.jwt", null)
        store.putString("account.$id.x25519", null)
        if (prefs.getString(activeKey, null) == id) {
            val fallback = list.firstOrNull()?.id
            prefs.edit().putString(activeKey, fallback).apply()
            _active.value = list.firstOrNull()
        }
    }

    @Serializable private data class ChalResp(val nonce_b64: String)
    @Serializable private data class VerifyReq(val username: String, val nonce_b64: String, val signature_b64: String)
    @Serializable private data class VerifyResp(val jwt: String)

    override suspend fun switchTo(id: String): SavedAccount = mutex.withLock {
        val acct = readList().firstOrNull { it.id == id } ?: throw AccountsError.Unknown
        val seedB64 = store.getString("account.$id.x25519") ?: throw AccountsError.ChallengeFailed
        val seed = Base64.decode(seedB64, Base64.DEFAULT)

        val nonceResp = runCatching {
            val resp = http.client.post("api/auth/challenge") {
                contentType(ContentType.Application.Json)
                setBody(mapOf("username" to acct.username))
            }
            if (!resp.status.isSuccess()) return@runCatching null
            resp.body<ChalResp>()
        }.getOrNull() ?: throw AccountsError.Refresh("challenge")

        val nonce = Base64.decode(nonceResp.nonce_b64, Base64.DEFAULT)
        val sig = signer.sign(seed, nonce)
        val verify = runCatching {
            val resp = http.client.post("api/auth/challenge/verify") {
                contentType(ContentType.Application.Json)
                setBody(VerifyReq(acct.username, nonceResp.nonce_b64, Base64.encodeToString(sig, Base64.NO_WRAP)))
            }
            if (!resp.status.isSuccess()) return@runCatching null
            resp.body<VerifyResp>()
        }.getOrNull() ?: throw AccountsError.Refresh("verify")

        store.putString("account.$id.jwt", verify.jwt)
        prefs.edit().putString(activeKey, id).apply()
        _active.value = acct
        acct
    }
}
