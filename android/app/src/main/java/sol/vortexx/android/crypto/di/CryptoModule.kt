package sol.vortexx.android.crypto.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.api.Kdf
import sol.vortexx.android.crypto.api.KeyAgreement
import sol.vortexx.android.crypto.api.PasswordHasher
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.api.Signer
import sol.vortexx.android.crypto.impl.AesGcmAead
import sol.vortexx.android.crypto.impl.Argon2idHasher
import sol.vortexx.android.crypto.impl.Ed25519Signer
import sol.vortexx.android.crypto.impl.HkdfSha256
import sol.vortexx.android.crypto.impl.SystemSecureRandom
import sol.vortexx.android.crypto.impl.X25519KeyAgreement
import javax.inject.Singleton

/**
 * Every crypto abstraction is bound exactly once here. To swap an algorithm
 * (e.g. AES-GCM → ChaCha20-Poly1305) we write a new impl and change the
 * binding — no consumer touches. That's the Dependency Inversion rule at
 * work: screens and view models depend on the interfaces above, never on
 * a BouncyCastle or JCE type directly.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class CryptoModule {

    @Binds @Singleton
    abstract fun bindSecureRandom(impl: SystemSecureRandom): SecureRandomProvider

    @Binds @Singleton
    abstract fun bindAead(impl: AesGcmAead): Aead

    @Binds @Singleton
    abstract fun bindKdf(impl: HkdfSha256): Kdf

    @Binds @Singleton
    abstract fun bindKeyAgreement(impl: X25519KeyAgreement): KeyAgreement

    @Binds @Singleton
    abstract fun bindSigner(impl: Ed25519Signer): Signer

    @Binds @Singleton
    abstract fun bindPasswordHasher(impl: Argon2idHasher): PasswordHasher
}
