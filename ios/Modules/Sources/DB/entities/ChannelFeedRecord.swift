import Foundation
import GRDB

public struct ChannelFeedRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var id: Int64
    public var roomId: Int64
    public var feedType: String       // "rss" | "atom" | "json"
    public var url: String
    public var lastFetched: Int64?
    public var isActive: Bool

    public static let databaseTableName = "channel_feeds"

    public init(id: Int64, roomId: Int64, feedType: String, url: String,
                lastFetched: Int64? = nil, isActive: Bool = true) {
        self.id = id; self.roomId = roomId; self.feedType = feedType
        self.url = url; self.lastFetched = lastFetched; self.isActive = isActive
    }
}
