import Foundation

/// One saved GIF from the per-user personal collection on the node.
/// Mirrors `/api/saved_gifs` (see web `saved_gifs.py`).
public struct SavedGif: Sendable, Codable, Hashable, Identifiable {
    public let id: Int64
    public let url: String
    public let width: Int
    public let height: Int
    public let addedAt: Int64
    public init(id: Int64, url: String, width: Int, height: Int, addedAt: Int64) {
        self.id = id; self.url = url; self.width = width; self.height = height; self.addedAt = addedAt
    }
}

/// No Tenor: only the user's own saved GIFs. The picker browses this
/// list; users can paste a URL or attach a file to grow it.
public protocol SavedGifs: Sendable {
    func list() async -> [SavedGif]
    func add(url: String, width: Int, height: Int) async -> SavedGif?
    func remove(id: Int64) async
}
