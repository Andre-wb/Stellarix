import Foundation

public protocol StickerCatalog: Sendable {
    var favorites: AsyncStream<[StickerPack]> { get }
    func refresh() async
    func addPack(_ id: String) async -> Bool
    func removePack(_ id: String) async -> Bool
}

public struct StickerPack: Sendable, Equatable {
    public let id: String
    public let name: String
    public let coverUrl: String
    public let stickerCount: Int
    public init(id: String, name: String, coverUrl: String, stickerCount: Int) {
        self.id = id; self.name = name; self.coverUrl = coverUrl; self.stickerCount = stickerCount
    }
}

public protocol VoiceRecorder: Sendable {
    /// Returns a session; caller calls `stop()` to retrieve bytes or `cancel()` to drop.
    func start() async throws -> VoiceSession
}

public protocol VoiceSession: Sendable {
    func stop() async -> Data
    func cancel() async
}
