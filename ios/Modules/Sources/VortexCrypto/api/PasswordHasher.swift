import Foundation

/// Password-based key derivation / verification (Argon2id).
///
/// `password` is passed as `Data` (expected UTF-8 encoded) rather than
/// `String` so callers can deterministically zero it after the call.
/// `String` in Swift is value-copied and interned by the runtime, making
/// a secure wipe impossible.
public protocol PasswordHasher: Sendable {
    func hash(password: Data, salt: Data, params: Argon2Params) throws -> Data

    /// Constant-time compare against `expected`.
    func verify(password: Data, salt: Data, expected: Data, params: Argon2Params) throws -> Bool
}

public extension PasswordHasher {
    func hash(password: Data, salt: Data) throws -> Data {
        try hash(password: password, salt: salt, params: .interactive())
    }
    func verify(password: Data, salt: Data, expected: Data) throws -> Bool {
        try verify(password: password, salt: salt, expected: expected, params: .interactive())
    }
}
