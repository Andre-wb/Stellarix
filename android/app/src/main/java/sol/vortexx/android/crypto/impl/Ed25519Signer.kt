package sol.vortexx.android.crypto.impl

import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer as BcEd25519Signer
import sol.vortexx.android.crypto.api.KeyPair
import sol.vortexx.android.crypto.api.SecureRandomProvider
import sol.vortexx.android.crypto.api.Signer
import java.security.SecureRandom
import javax.inject.Inject

/**
 * Ed25519 — RFC 8032. Raw 32-byte private + 32-byte public, 64-byte signature,
 * matching the manifest signing done in the controller's sign_tool.py.
 */
class Ed25519Signer @Inject constructor(
    private val random: SecureRandomProvider,
) : Signer {

    override fun generateKeyPair(): KeyPair {
        val priv = Ed25519PrivateKeyParameters(BridgedRandom(random))
        val pub  = priv.generatePublicKey()
        return KeyPair(priv.encoded.copyOf(), pub.encoded.copyOf())
    }

    override fun sign(privateKey: ByteArray, message: ByteArray): ByteArray {
        require(privateKey.size == KEY_LEN) { "Ed25519 private key must be $KEY_LEN bytes" }
        val s = BcEd25519Signer().apply {
            init(true, Ed25519PrivateKeyParameters(privateKey, 0))
            update(message, 0, message.size)
        }
        return s.generateSignature()
    }

    override fun verify(publicKey: ByteArray, message: ByteArray, signature: ByteArray): Boolean {
        if (publicKey.size != KEY_LEN || signature.size != SIG_LEN) return false
        val v = BcEd25519Signer().apply {
            init(false, Ed25519PublicKeyParameters(publicKey, 0))
            update(message, 0, message.size)
        }
        return v.verifySignature(signature)
    }

    private class BridgedRandom(private val p: SecureRandomProvider) : SecureRandom() {
        override fun nextBytes(bytes: ByteArray) {
            val r = p.nextBytes(bytes.size)
            System.arraycopy(r, 0, bytes, 0, bytes.size)
        }
    }

    private companion object {
        const val KEY_LEN = 32
        const val SIG_LEN = 64
    }
}
