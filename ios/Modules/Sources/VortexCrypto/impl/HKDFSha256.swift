import Foundation
import CryptoKit

/// HKDF-SHA256 (RFC 5869). Stateless — just a thin wrapper over CryptoKit's
/// `HKDF<SHA256>.deriveKey(...)` that exposes the raw byte output.
public final class HKDFSha256: Kdf {
    private let hashLen = 32
    private let maxOut: Int

    public init() { self.maxOut = 255 * hashLen }

    public func derive(ikm: Data, salt: Data, info: Data, length: Int) throws -> Data {
        guard length > 0 && length <= maxOut else {
            throw KdfError.outputTooLong(requested: length, max: maxOut)
        }
        let inputKey = SymmetricKey(data: ikm)
        let derived = HKDF<SHA256>.deriveKey(
            inputKeyMaterial: inputKey,
            salt: salt,
            info: info,
            outputByteCount: length,
        )
        return derived.withUnsafeBytes { Data($0) }
    }
}
