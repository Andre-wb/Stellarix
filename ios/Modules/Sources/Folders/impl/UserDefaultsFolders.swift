import Foundation

/// UserDefaults-backed implementation. All writes are synchronous; the
/// UI observes via an `ObservableObject` wrapper built on top of this.
public final class UserDefaultsFolders: Folders, @unchecked Sendable {
    private let defaults: UserDefaults
    private let foldersKey = "vortex.folders"
    private let archivedKey = "vortex.archived"
    private let lock = NSLock()

    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    private struct StoredFolder: Codable {
        let id: String
        let title: String
        let roomIds: [Int64]
    }

    private func loadStored() -> [StoredFolder] {
        guard let raw = defaults.data(forKey: foldersKey),
              let list = try? JSONDecoder().decode([StoredFolder].self, from: raw) else { return [] }
        return list
    }

    private func saveStored(_ list: [StoredFolder]) {
        if let raw = try? JSONEncoder().encode(list) {
            defaults.set(raw, forKey: foldersKey)
        }
    }

    public func list() -> [ChatFolder] {
        lock.lock(); defer { lock.unlock() }
        let arch = archivedRaw()
        let all = ChatFolder(id: "all", title: "All", roomIds: [], isSystem: true)
        let archived = ChatFolder(id: "archived", title: "Archived", roomIds: arch, isSystem: true)
        let custom = loadStored().map {
            ChatFolder(id: $0.id, title: $0.title, roomIds: Set($0.roomIds))
        }
        return [all, archived] + custom
    }

    public func create(title: String, roomIds: Set<Int64>) -> ChatFolder {
        lock.lock(); defer { lock.unlock() }
        let id = "f-\(Int(Date().timeIntervalSince1970 * 1000))"
        var list = loadStored()
        list.append(.init(id: id, title: title, roomIds: Array(roomIds)))
        saveStored(list)
        return ChatFolder(id: id, title: title, roomIds: roomIds)
    }

    public func delete(id: String) {
        lock.lock(); defer { lock.unlock() }
        var list = loadStored()
        list.removeAll { $0.id == id }
        saveStored(list)
    }

    public func rename(id: String, to newTitle: String) {
        lock.lock(); defer { lock.unlock() }
        var list = loadStored()
        if let idx = list.firstIndex(where: { $0.id == id }) {
            list[idx] = .init(id: id, title: newTitle, roomIds: list[idx].roomIds)
            saveStored(list)
        }
    }

    public func setMembers(id: String, roomIds: Set<Int64>) {
        lock.lock(); defer { lock.unlock() }
        var list = loadStored()
        if let idx = list.firstIndex(where: { $0.id == id }) {
            list[idx] = .init(id: id, title: list[idx].title, roomIds: Array(roomIds))
            saveStored(list)
        }
    }

    private func archivedRaw() -> Set<Int64> {
        Set((defaults.array(forKey: archivedKey) as? [NSNumber])?.map { $0.int64Value } ?? [])
    }

    public func archive(roomId: Int64) {
        lock.lock(); defer { lock.unlock() }
        var s = archivedRaw(); s.insert(roomId)
        defaults.set(s.map { NSNumber(value: $0) }, forKey: archivedKey)
    }

    public func unarchive(roomId: Int64) {
        lock.lock(); defer { lock.unlock() }
        var s = archivedRaw(); s.remove(roomId)
        defaults.set(s.map { NSNumber(value: $0) }, forKey: archivedKey)
    }

    public func archived() -> Set<Int64> {
        lock.lock(); defer { lock.unlock() }
        return archivedRaw()
    }
}
