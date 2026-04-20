import Foundation

/// Asymmetric key agreement (X25519).
///
/// Responsibility ends at producing a raw 32-byte shared secret. HKDF or
/// any post-processing lives in [Kdf] — this split keeps the interface
/// swappable for Kyber / X448 without touching consumers.
public protocol KeyAgreement: Sendable {
    func generateKeyPair() -> KeyPair
    func agree(myPrivate: Data, theirPublic: Data) throws -> Data
}

public enum KeyAgreementError: Error {
    case invalidKeyLength(Int)
}
