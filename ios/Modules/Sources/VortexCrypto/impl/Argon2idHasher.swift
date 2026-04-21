import Foundation
import Argon2Swift

/// Argon2id (RFC 9106) via the `Argon2Swift` bridge over libargon2.
///
/// Passwords arrive as `Data` (UTF-8) so the caller can zero the buffer
/// after the call. The hash is derived deterministically from
/// (password, salt, params), so the caller persists [Argon2Params] with
/// the salt to verify later without extra metadata.
public final class Argon2idHasher: PasswordHasher {
    public init() {}

    public func hash(password: Data, salt: Data, params: Argon2Params) throws -> Data {
        let saltObj = Salt(bytes: salt)
        let result = try Argon2Swift.hashPasswordBytes(
            password: password,
            salt: saltObj,
            iterations: Int(params.iterations),
            memory: Int(params.memoryKiB),
            parallelism: Int(params.parallelism),
            length: Int(params.hashLen),
            type: Argon2Type.id,
            version: Argon2Version.V13,
        )
        return result.hashData()
    }

    public func verify(password: Data, salt: Data, expected: Data, params: Argon2Params) throws -> Bool {
        let got = try hash(password: password, salt: salt, params: params)
        return constantTimeEquals(got, expected)
    }

    private func constantTimeEquals(_ a: Data, _ b: Data) -> Bool {
        guard a.count == b.count else { return false }
        var diff: UInt8 = 0
        for i in 0..<a.count { diff |= a[i] ^ b[i] }
        return diff == 0
    }
}
