package sol.vortexx.android.crypto.impl

import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.api.AeadAuthenticationException
import sol.vortexx.android.crypto.api.SecureRandomProvider
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import javax.inject.Inject

/**
 * AES-256-GCM via the JCE provider bundled with Android — no native deps.
 *
 * Wire format matches the Vortex server's `ciphertext_hex`:
 *     nonce(12 bytes) || ciphertext || auth_tag(16 bytes)
 * so a hex-encoded payload round-trips unchanged between the Python node,
 * the web client, and this impl.
 *
 * A fresh 12-byte nonce is drawn per encryption from [SecureRandomProvider].
 * Nonce reuse under GCM is catastrophic — we never let the caller supply
 * one, so there is no API path that can accidentally collide.
 */
class AesGcmAead @Inject constructor(
    private val random: SecureRandomProvider,
) : Aead {

    override fun encrypt(key: ByteArray, plaintext: ByteArray, aad: ByteArray): ByteArray {
        requireKey(key)
        val nonce = random.nextBytes(NONCE_LEN)
        val cipher = Cipher.getInstance(TRANSFORM).apply {
            init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(TAG_BITS, nonce))
            if (aad.isNotEmpty()) updateAAD(aad)
        }
        val ct = cipher.doFinal(plaintext)          // ct here = ciphertext || tag
        return nonce + ct
    }

    override fun decrypt(key: ByteArray, packed: ByteArray, aad: ByteArray): ByteArray {
        requireKey(key)
        require(packed.size >= NONCE_LEN + TAG_LEN) { "ciphertext too short" }
        val nonce = packed.copyOfRange(0, NONCE_LEN)
        val body  = packed.copyOfRange(NONCE_LEN, packed.size)
        val cipher = Cipher.getInstance(TRANSFORM).apply {
            init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(TAG_BITS, nonce))
            if (aad.isNotEmpty()) updateAAD(aad)
        }
        return try {
            cipher.doFinal(body)
        } catch (e: javax.crypto.AEADBadTagException) {
            throw AeadAuthenticationException("AES-GCM tag mismatch", e)
        } catch (e: javax.crypto.BadPaddingException) {
            // Some providers surface a tag mismatch as BadPadding — treat equivalently.
            throw AeadAuthenticationException("AES-GCM authentication failed", e)
        }
    }

    private fun requireKey(key: ByteArray) {
        require(key.size == KEY_LEN) { "AES-256-GCM requires a 32-byte key, got ${key.size}" }
    }

    private companion object {
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val KEY_LEN   = 32
        const val NONCE_LEN = 12
        const val TAG_LEN   = 16
        const val TAG_BITS  = TAG_LEN * 8
    }
}
