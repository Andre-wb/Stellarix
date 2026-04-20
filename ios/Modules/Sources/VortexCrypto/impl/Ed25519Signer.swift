import Foundation
import CryptoKit

/// Ed25519 (RFC 8032). Raw 32/32 keys, 64-byte signature — matches the
/// Python controller's `sign_tool.py` so manifest pubkeys are wire-
/// compatible.
public final class Ed25519Signer: Signer {
    public init() {}

    public func generateKeyPair() -> KeyPair {
        let priv = Curve25519.Signing.PrivateKey()
        return KeyPair(
            privateKey: priv.rawRepresentation,
            publicKey:  priv.publicKey.rawRepresentation,
        )
    }

    public func sign(privateKey: Data, message: Data) throws -> Data {
        guard privateKey.count == 32 else { throw SignerError.invalidKeyLength(privateKey.count) }
        let priv = try Curve25519.Signing.PrivateKey(rawRepresentation: privateKey)
        return try priv.signature(for: message)
    }

    public func verify(publicKey: Data, message: Data, signature: Data) -> Bool {
        guard publicKey.count == 32, signature.count == 64 else { return false }
        return (try? Curve25519.Signing.PublicKey(rawRepresentation: publicKey))?
            .isValidSignature(signature, for: message) ?? false
    }
}
