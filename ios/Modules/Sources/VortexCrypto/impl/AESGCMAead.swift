import Foundation
import CryptoKit

/// AES-256-GCM via Apple CryptoKit. Hardware-accelerated on every
/// current iPhone (AES instructions in the Secure Enclave-adjacent CPU).
///
/// Wire format: `nonce(12) || ciphertext || tag(16)` — identical to the
/// Kotlin `AesGcmAead` and the Vortex server's `ciphertext_hex`. A fresh
/// 12-byte nonce is drawn per encryption from [SecureRandomProvider];
/// nonce reuse under GCM is catastrophic so the API never lets callers
/// supply one.
public final class AESGCMAead: Aead {
    private let random: SecureRandomProvider

    public init(random: SecureRandomProvider) {
        self.random = random
    }

    public func encrypt(key: Data, plaintext: Data, aad: Data) throws -> Data {
        guard key.count == 32 else { throw AeadError.invalidKeyLength(key.count) }
        let sk = SymmetricKey(data: key)
        let nonceBytes = random.nextBytes(12)
        let nonce = try AES.GCM.Nonce(data: nonceBytes)
        let sealed = try AES.GCM.seal(plaintext, using: sk, nonce: nonce, authenticating: aad)
        // CryptoKit's `.combined` is nonce||ciphertext||tag — exactly our format.
        guard let combined = sealed.combined else {
            throw AeadError.authenticationFailed("sealed.combined was nil")
        }
        return combined
    }

    public func decrypt(key: Data, packed: Data, aad: Data) throws -> Data {
        guard key.count == 32 else { throw AeadError.invalidKeyLength(key.count) }
        guard packed.count >= 12 + 16 else { throw AeadError.ciphertextTooShort }
        let sk = SymmetricKey(data: key)
        do {
            let box = try AES.GCM.SealedBox(combined: packed)
            return try AES.GCM.open(box, using: sk, authenticating: aad)
        } catch let err as CryptoKitError {
            throw AeadError.authenticationFailed(String(describing: err))
        }
    }
}
