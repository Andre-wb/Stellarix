import Foundation

/// Persistent storage of the user-chosen node URL.
///
/// Narrow on purpose — JWTs and keys live in Keychain (Wave 5). Only
/// what we need to boot: the node base URL.
public protocol NodePreferences: Sendable {
    var baseUrlStream: AsyncStream<String?> { get }
    func currentBaseUrl() -> String?
    func setBaseUrl(_ url: String?)
}
