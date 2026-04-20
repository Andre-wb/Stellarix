import Foundation

/// Digital signature (Ed25519 by default).
///
/// Raw 32-byte private + 32-byte public, 64-byte signature, matching the
/// manifest signing done by the Python controller's `sign_tool.py`.
public protocol Signer: Sendable {
    func generateKeyPair() -> KeyPair
    func sign(privateKey: Data, message: Data) throws -> Data
    func verify(publicKey: Data, message: Data, signature: Data) -> Bool
}

public enum SignerError: Error {
    case invalidKeyLength(Int)
}
