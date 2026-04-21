import Foundation

/// A named group of rooms, plus two pseudo-folders (`All` and
/// `Archived`) that the UI always shows.
public struct ChatFolder: Sendable, Hashable, Identifiable {
    public let id: String       // stable slug: "all","archived","work", …
    public let title: String
    public let roomIds: Set<Int64>
    public let isSystem: Bool   // true for "all" / "archived"

    public init(id: String, title: String, roomIds: Set<Int64>, isSystem: Bool = false) {
        self.id = id; self.title = title; self.roomIds = roomIds; self.isSystem = isSystem
    }
}

/// Local-only (no server endpoint yet) store for folders and the
/// archived-rooms list. Persisted to UserDefaults under
/// "vortex.folders" (JSON) and "vortex.archived" (JSON array of ints).
public protocol Folders: Sendable {
    func list() -> [ChatFolder]
    func create(title: String, roomIds: Set<Int64>) -> ChatFolder
    func delete(id: String)
    func rename(id: String, to: String)
    func setMembers(id: String, roomIds: Set<Int64>)
    func archive(roomId: Int64)
    func unarchive(roomId: Int64)
    func archived() -> Set<Int64>
}
