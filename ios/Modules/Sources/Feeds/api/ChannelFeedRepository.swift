import Foundation

public protocol ChannelFeedRepository: Sendable {
    func observe(_ roomId: Int64) -> AsyncStream<[ChannelFeed]>
    func refresh(_ roomId: Int64) async -> Bool
    func subscribe(roomId: Int64, url: String, feedType: String) async -> Bool
    func unsubscribe(_ feedId: Int64) async -> Bool
}

public struct ChannelFeed: Sendable, Equatable {
    public let id: Int64
    public let roomId: Int64
    public let feedType: String
    public let url: String
    public let lastFetched: Int64?
    public let isActive: Bool
    public init(id: Int64, roomId: Int64, feedType: String, url: String,
                lastFetched: Int64?, isActive: Bool) {
        self.id = id; self.roomId = roomId; self.feedType = feedType
        self.url = url; self.lastFetched = lastFetched; self.isActive = isActive
    }
}
