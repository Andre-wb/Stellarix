import Foundation

/// One saved account that the user can switch to. The secret-sensitive
/// material (JWT / X25519 static key) lives in the Keychain; only the
/// metadata-sized fields survive in the per-account list.
public struct SavedAccount: Sendable, Codable, Hashable, Identifiable {
    public let id: String             // stable GUID
    public let baseUrl: String        // node the account is registered on
    public let username: String
    public let userId: Int64?
    public let addedAt: Int64         // unix ms

    public init(id: String, baseUrl: String, username: String, userId: Int64?, addedAt: Int64) {
        self.id = id; self.baseUrl = baseUrl; self.username = username
        self.userId = userId; self.addedAt = addedAt
    }
}

/// Manages a list of saved accounts and "which one is currently active".
/// Switching performs an X25519 challenge-response refresh against the
/// account's node — matching the web client's `switchAccount()` flow.
public protocol AccountsManager: Sendable {
    func list() async -> [SavedAccount]
    func active() async -> SavedAccount?
    func add(_ account: SavedAccount, jwt: String, staticKeySeedB64: String) async
    func remove(id: String) async
    func switchTo(id: String) async throws -> SavedAccount
}

public enum AccountsError: Error, Equatable {
    case unknownAccount
    case challengeFailed
    case refreshFailed(String)
}
