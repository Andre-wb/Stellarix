import Foundation
import Security

/// [SecureRandomProvider] backed by Apple's `SecRandomCopyBytes`, which
/// pulls from `/dev/random`-equivalent kernel CSPRNG. Thread-safe at the
/// kernel boundary, no local state to guard.
public final class SystemSecureRandom: SecureRandomProvider {
    public init() {}

    public func nextBytes(_ length: Int) -> Data {
        precondition(length >= 0, "length must be non-negative")
        if length == 0 { return Data() }
        var bytes = Data(count: length)
        let status = bytes.withUnsafeMutableBytes { buf -> OSStatus in
            guard let base = buf.baseAddress else { return errSecParam }
            return SecRandomCopyBytes(kSecRandomDefault, length, base)
        }
        precondition(status == errSecSuccess, "SecRandomCopyBytes failed: \(status)")
        return bytes
    }
}
