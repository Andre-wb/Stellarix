import Foundation

/// Composition helper — builds the default CryptoKit-backed stack.
///
/// `AppEnvironment` calls this once at startup and passes the resulting
/// types into downstream features. Tests wire their own implementations
/// of the protocols instead of calling this factory.
public struct VortexCryptoFactory {
    public let random: SecureRandomProvider
    public let aead:   Aead
    public let kdf:    Kdf
    public let keyAgreement: KeyAgreement
    public let signer: Signer
    public let passwordHasher: PasswordHasher

    public init(random: SecureRandomProvider = SystemSecureRandom()) {
        self.random = random
        self.aead = AESGCMAead(random: random)
        self.kdf = HKDFSha256()
        self.keyAgreement = X25519KeyAgreement()
        self.signer = Ed25519Signer()
        self.passwordHasher = Argon2idHasher()
    }
}
