import Foundation

/// Authenticated Encryption with Associated Data.
///
/// Wire format matches the Vortex server's `ciphertext_hex`:
///     nonce(12) || ciphertext || tag(16)
/// so a hex-encoded payload round-trips unchanged between the Python
/// node, the web client, Android (Kotlin `AesGcmAead`), and this impl.
public protocol Aead: Sendable {
    /// Encrypt `plaintext` returning `nonce || ciphertext || tag`.
    func encrypt(key: Data, plaintext: Data, aad: Data) throws -> Data

    /// Decrypt a packed blob produced by [encrypt].
    /// Throws [AeadError.authenticationFailed] on tag mismatch.
    func decrypt(key: Data, packed: Data, aad: Data) throws -> Data
}

public extension Aead {
    func encrypt(key: Data, plaintext: Data) throws -> Data {
        try encrypt(key: key, plaintext: plaintext, aad: Data())
    }
    func decrypt(key: Data, packed: Data) throws -> Data {
        try decrypt(key: key, packed: packed, aad: Data())
    }
}

public enum AeadError: Error, Equatable {
    case invalidKeyLength(Int)
    case ciphertextTooShort
    case authenticationFailed(String)
}
