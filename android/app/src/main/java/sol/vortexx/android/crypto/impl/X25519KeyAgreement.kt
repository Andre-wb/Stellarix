package sol.vortexx.android.crypto.impl

import org.bouncycastle.crypto.agreement.X25519Agreement
import org.bouncycastle.crypto.params.X25519PrivateKeyParameters
import org.bouncycastle.crypto.params.X25519PublicKeyParameters
import sol.vortexx.android.crypto.api.KeyAgreement
import sol.vortexx.android.crypto.api.KeyPair
import sol.vortexx.android.crypto.api.SecureRandomProvider
import java.security.SecureRandom
import javax.inject.Inject

/**
 * X25519 ECDH — RFC 7748.
 *
 * Relies on BouncyCastle so the same code path runs on API 26 (where the
 * platform's java.security.spec.NamedParameterSpec is missing) and on
 * API 34. Randomness is proxied through [SecureRandomProvider] so tests
 * can pin keys for known-answer vectors.
 */
class X25519KeyAgreement @Inject constructor(
    private val random: SecureRandomProvider,
) : KeyAgreement {

    override fun generateKeyPair(): KeyPair {
        // BC's constructor takes a java.security.SecureRandom; we bridge it
        // to our provider so injection can override the entropy source.
        val priv = X25519PrivateKeyParameters(BridgedRandom(random))
        val pub  = priv.generatePublicKey()
        return KeyPair(
            privateKey = priv.encoded.copyOf(),
            publicKey  = pub.encoded.copyOf(),
        )
    }

    override fun agree(myPrivate: ByteArray, theirPublic: ByteArray): ByteArray {
        require(myPrivate.size == KEY_LEN && theirPublic.size == KEY_LEN) {
            "X25519 keys must be $KEY_LEN bytes"
        }
        val agree = X25519Agreement()
        agree.init(X25519PrivateKeyParameters(myPrivate, 0))
        val shared = ByteArray(agree.agreementSize)
        agree.calculateAgreement(X25519PublicKeyParameters(theirPublic, 0), shared, 0)
        return shared
    }

    /** Adapter: routes BouncyCastle's SecureRandom calls through our provider. */
    private class BridgedRandom(private val p: SecureRandomProvider) : SecureRandom() {
        override fun nextBytes(bytes: ByteArray) {
            val r = p.nextBytes(bytes.size)
            System.arraycopy(r, 0, bytes, 0, bytes.size)
        }
    }

    private companion object { const val KEY_LEN = 32 }
}
