import Foundation

public struct Contact: Sendable, Codable, Hashable, Identifiable {
    public let id: Int64           // user id on this node
    public let username: String
    public let displayName: String?
    public let avatarUrl: String?
    public let addedAt: Int64

    public init(id: Int64, username: String, displayName: String?, avatarUrl: String?, addedAt: Int64) {
        self.id = id; self.username = username; self.displayName = displayName
        self.avatarUrl = avatarUrl; self.addedAt = addedAt
    }
}

/// Per-user contact list persisted on the node (see web
/// `contacts.py`). Only mutual-follow style; no off-node address book.
public protocol Contacts: Sendable {
    func list() async -> [Contact]
    func add(username: String) async -> Contact?
    func remove(id: Int64) async
    func search(_ query: String) async -> [Contact]
}
