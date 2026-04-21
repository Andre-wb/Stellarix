package sol.vortexx.android.accounts.api

import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.Serializable

@Serializable
data class SavedAccount(
    val id: String,
    val baseUrl: String,
    val username: String,
    val userId: Long?,
    val addedAt: Long,
)

sealed class AccountsError(msg: String) : Exception(msg) {
    data object Unknown : AccountsError("unknown account")
    data object ChallengeFailed : AccountsError("challenge failed")
    data class Refresh(val detail: String) : AccountsError("refresh failed: $detail")
}

interface Accounts {
    val list: StateFlow<List<SavedAccount>>
    val active: StateFlow<SavedAccount?>

    suspend fun add(account: SavedAccount, jwt: String, staticKeySeedB64: String)
    suspend fun remove(id: String)
    suspend fun switchTo(id: String): SavedAccount
}
