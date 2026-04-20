import Foundation

/// HKDF-SHA256 (RFC 5869).
///
/// Narrow by design — password-based derivation lives in [PasswordHasher]
/// because it needs memory/iteration knobs HKDF doesn't carry.
public protocol Kdf: Sendable {
    func derive(ikm: Data, salt: Data, info: Data, length: Int) throws -> Data
}

public extension Kdf {
    func derive(ikm: Data, salt: Data = Data(), info: Data = Data(), length: Int = 32) throws -> Data {
        try derive(ikm: ikm, salt: salt, info: info, length: length)
    }
}

public enum KdfError: Error {
    case outputTooLong(requested: Int, max: Int)
}
