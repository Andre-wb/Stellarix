package sol.vortexx.android.identity.impl

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters
import org.bouncycastle.crypto.params.X25519PrivateKeyParameters
import sol.vortexx.android.auth.api.SecureStore
import sol.vortexx.android.crypto.api.KeyPair
import sol.vortexx.android.crypto.api.Kdf
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.identity.api.Identity
import sol.vortexx.android.identity.api.IdentityRepository
import sol.vortexx.android.identity.api.Mnemonic
import sol.vortexx.android.identity.api.SeedProvider
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Derives and persists the device identity.
 *
 * On first call: generate mnemonic → derive 64-byte seed → HKDF split
 * into an X25519 seed and an Ed25519 seed → generate the two keypairs.
 * Mnemonic + private keys land in [SecureStore]; public keys are
 * exported to non-secure DataStore (Wave 8+) so lookup doesn't touch
 * the Keystore every frame.
 */
@Singleton
class SeedIdentityRepository @Inject constructor(
    private val seeds: SeedProvider,
    private val kdf: Kdf,
    private val store: SecureStore,
) : IdentityRepository {

    private val _identity = MutableStateFlow<Identity?>(loadFromStore())
    override val identity = _identity.asStateFlow()

    override suspend fun createOrLoad(): Identity {
        _identity.value?.let { return it }

        // Consult SecureStore again — an out-of-band restore (e.g. key-backup
        // flow) can have populated it after wipe(). Without this step we'd
        // generate a brand new mnemonic and overwrite the restored one.
        loadFromStore()?.let {
            _identity.value = it
            return it
        }

        val mnemonic = seeds.generate()
        val seed = seeds.toSeed(mnemonic)
        val id = deriveIdentity(mnemonic, seed)
        persist(id)
        _identity.value = id
        return id
    }

    override suspend fun wipe() {
        store.putString(KEY_MNEMONIC, null)
        store.putString(KEY_X25519_PRIV, null)
        store.putString(KEY_X25519_PUB,  null)
        store.putString(KEY_ED25519_PRIV, null)
        store.putString(KEY_ED25519_PUB,  null)
        _identity.value = null
    }

    // ── internals ──────────────────────────────────────────────────────

    private fun deriveIdentity(mnemonic: Mnemonic, seed: ByteArray): Identity {
        // Domain-separated HKDF: one derivation per key role so rotating
        // one of them doesn't leak the other.
        val xSeed = kdf.derive(ikm = seed, info = "vortex/x25519".toByteArray(), length = 32)
        val eSeed = kdf.derive(ikm = seed, info = "vortex/ed25519".toByteArray(), length = 32)

        val xPriv = X25519PrivateKeyParameters(xSeed, 0)
        val ePriv = Ed25519PrivateKeyParameters(eSeed, 0)
        return Identity(
            mnemonic = mnemonic,
            x25519  = KeyPair(privateKey = xPriv.encoded.copyOf(), publicKey = xPriv.generatePublicKey().encoded.copyOf()),
            ed25519 = KeyPair(privateKey = ePriv.encoded.copyOf(), publicKey = ePriv.generatePublicKey().encoded.copyOf()),
        )
    }

    private fun persist(id: Identity) {
        store.putString(KEY_MNEMONIC,      id.mnemonic.toString())
        store.putString(KEY_X25519_PRIV,   Hex.encode(id.x25519.privateKey))
        store.putString(KEY_X25519_PUB,    Hex.encode(id.x25519.publicKey))
        store.putString(KEY_ED25519_PRIV,  Hex.encode(id.ed25519.privateKey))
        store.putString(KEY_ED25519_PUB,   Hex.encode(id.ed25519.publicKey))
    }

    private fun loadFromStore(): Identity? {
        val words = store.getString(KEY_MNEMONIC) ?: return null
        return runCatching {
            Identity(
                mnemonic = Mnemonic(words.split(' ')),
                x25519  = KeyPair(
                    privateKey = Hex.decode(store.getString(KEY_X25519_PRIV)!!),
                    publicKey  = Hex.decode(store.getString(KEY_X25519_PUB )!!),
                ),
                ed25519 = KeyPair(
                    privateKey = Hex.decode(store.getString(KEY_ED25519_PRIV)!!),
                    publicKey  = Hex.decode(store.getString(KEY_ED25519_PUB )!!),
                ),
            )
        }.getOrNull()
    }

    private companion object {
        const val KEY_MNEMONIC      = "id_mnemonic"
        const val KEY_X25519_PRIV   = "id_x25519_priv"
        const val KEY_X25519_PUB    = "id_x25519_pub"
        const val KEY_ED25519_PRIV  = "id_ed25519_priv"
        const val KEY_ED25519_PUB   = "id_ed25519_pub"
    }
}
