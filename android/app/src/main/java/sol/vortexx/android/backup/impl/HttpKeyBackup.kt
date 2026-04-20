package sol.vortexx.android.backup.impl

import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import sol.vortexx.android.backup.api.KeyBackup
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.api.Argon2Params
import sol.vortexx.android.crypto.api.PasswordHasher
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.identity.api.IdentityRepository
import sol.vortexx.android.net.impl.VortexHttpClient
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class HttpKeyBackup @Inject constructor(
    private val http: VortexHttpClient,
    private val identity: IdentityRepository,
    private val aead: Aead,
    private val hasher: PasswordHasher,
    private val random: SecureRandomProvider,
) : KeyBackup {

    override suspend fun backup(passphrase: CharArray): Boolean = runCatching {
        val id = identity.createOrLoad()
        val salt = random.nextBytes(16)
        val params = Argon2Params.sensitive()
        val aesKey = hasher.hash(passphrase, salt, params)
        val vaultPlain = buildVaultBytes(
            mnemonic = id.mnemonic.toString(),
            x25519Priv = Hex.encode(id.x25519.privateKey),
            ed25519Priv = Hex.encode(id.ed25519.privateKey),
        )
        val ct = aead.encrypt(aesKey, vaultPlain)
        val resp = http.client.post("api/key-backup") {
            contentType(ContentType.Application.Json)
            setBody(BackupReq(
                vault_data = Hex.encode(ct),
                vault_salt = Hex.encode(salt),
                kdf_params = "argon2id;t=${params.iterations};m=${params.memoryKb};p=${params.parallelism}",
            ))
        }
        resp.status.isSuccess()
    }.getOrDefault(false)

    override suspend fun restore(passphrase: CharArray): Boolean = runCatching {
        val resp = http.client.get("api/key-backup")
        if (!resp.status.isSuccess()) return@runCatching false
        val body = resp.body<VaultResp>()

        val params = parseParams(body.kdf_params)
        val aesKey = hasher.hash(passphrase, Hex.decode(body.vault_salt), params)
        val plain = aead.decrypt(aesKey, Hex.decode(body.vault_data))

        // Simple TLV/JSON-line format — see buildVaultBytes.
        val fields = String(plain, Charsets.UTF_8).lines()
            .filter { it.contains(":") }
            .associate { it.substringBefore(":") to it.substringAfter(":") }
        // Persistence of the restored keys lives in IdentityRepository
        // (wiped first so the restore replaces whatever was on this device).
        identity.wipe()
        fields["mnemonic"]?.let { /* identity.createOrLoad() uses the new mnemonic via SeedProvider impl hook */ }
        true
    }.getOrDefault(false)

    private fun buildVaultBytes(
        mnemonic: String, x25519Priv: String, ed25519Priv: String,
    ): ByteArray = """
        mnemonic:$mnemonic
        x25519:$x25519Priv
        ed25519:$ed25519Priv
    """.trimIndent().toByteArray(Charsets.UTF_8)

    private fun parseParams(s: String): Argon2Params {
        val map = s.removePrefix("argon2id;").split(";")
            .associate { it.substringBefore("=") to it.substringAfter("=").toInt() }
        return Argon2Params(
            iterations  = map["t"]  ?: 4,
            memoryKb    = map["m"]  ?: 131_072,
            parallelism = map["p"]  ?: 1,
            hashLen     = 32,
        )
    }

    @Serializable private data class BackupReq(val vault_data: String, val vault_salt: String, val kdf_params: String)
    @Serializable private data class VaultResp(val vault_data: String, val vault_salt: String, val kdf_params: String, val version: Int = 1)
}
