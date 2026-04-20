import Foundation

public protocol SpaceDao: Sendable {
    func observeAll() -> AsyncStream<[SpaceRecord]>
    func upsertAll(_ rows: [SpaceRecord]) async throws
    func delete(_ id: Int64) async throws
}

public protocol BotDao: Sendable {
    func observeMarketplace() -> AsyncStream<[BotRecord]>
    func observeInstalled() -> AsyncStream<[BotRecord]>
    func upsertAll(_ rows: [BotRecord]) async throws
    func setInstalled(_ id: Int64, _ installed: Bool) async throws
}

public protocol ThreadDao: Sendable {
    func observeForRoom(_ roomId: Int64) -> AsyncStream<[ThreadRecord]>
    func upsertAll(_ rows: [ThreadRecord]) async throws
}

public protocol ChannelFeedDao: Sendable {
    func observeForRoom(_ roomId: Int64) -> AsyncStream<[ChannelFeedRecord]>
    func upsert(_ row: ChannelFeedRecord) async throws
    func delete(_ id: Int64) async throws
}

public protocol ReactionDao: Sendable {
    func observeForMessage(_ id: Int64) -> AsyncStream<[ReactionRecord]>
    func upsert(_ r: ReactionRecord) async throws
    func remove(messageId: Int64, userId: Int64, emoji: String) async throws
}

public protocol ReadReceiptDao: Sendable {
    func latest(roomId: Int64, userId: Int64) async throws -> Int64?
    func upsert(_ r: ReadReceiptRecord) async throws
}

public protocol SearchDao: Sendable {
    func index(id: Int64, plaintext: String) async throws
    func unindex(_ id: Int64) async throws
    func search(_ query: String, limit: Int) async throws -> [MessageRecord]
}
