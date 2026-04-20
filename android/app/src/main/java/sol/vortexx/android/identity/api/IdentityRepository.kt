package sol.vortexx.android.identity.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.crypto.api.KeyPair

/**
 * User cryptographic identity — lives on this device only, derived from
 * the seed phrase. Both the X25519 (encryption / ECDH) and Ed25519
 * (signing) keypairs are always present together — a half-initialised
 * state is a bug, not a feature.
 */
interface IdentityRepository {
    val identity: Flow<Identity?>
    suspend fun createOrLoad(): Identity
    suspend fun wipe()
}

data class Identity(
    val mnemonic: Mnemonic,
    val x25519: KeyPair,   // privateKey / publicKey — 32/32 bytes raw
    val ed25519: KeyPair,  // ditto
)
