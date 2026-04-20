import Foundation
import CryptoKit

/// X25519 ECDH (RFC 7748) via CryptoKit's `Curve25519.KeyAgreement`.
///
/// Apple's API returns the raw 32-byte shared secret when we ask for
/// `sharedSecretFromKeyAgreement(with:).withUnsafeBytes { Data($0) }`
/// — i.e. without the HKDF step that `sharedSecretFromKeyAgreement`
/// optionally folds in. That keeps us consistent with the Vortex server
/// which does HKDF *after* the raw DH separately.
public final class X25519KeyAgreement: KeyAgreement {
    public init() {}

    public func generateKeyPair() -> KeyPair {
        let priv = Curve25519.KeyAgreement.PrivateKey()
        return KeyPair(
            privateKey: priv.rawRepresentation,
            publicKey:  priv.publicKey.rawRepresentation,
        )
    }

    public func agree(myPrivate: Data, theirPublic: Data) throws -> Data {
        guard myPrivate.count == 32, theirPublic.count == 32 else {
            throw KeyAgreementError.invalidKeyLength(myPrivate.count)
        }
        let priv = try Curve25519.KeyAgreement.PrivateKey(rawRepresentation: myPrivate)
        let pub  = try Curve25519.KeyAgreement.PublicKey(rawRepresentation: theirPublic)
        let shared = try priv.sharedSecretFromKeyAgreement(with: pub)
        return shared.withUnsafeBytes { Data($0) }
    }
}
