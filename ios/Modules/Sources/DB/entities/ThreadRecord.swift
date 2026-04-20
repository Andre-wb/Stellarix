import Foundation
import GRDB

public struct ThreadRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var id: Int64
    public var roomId: Int64
    public var parentMessageId: Int64
    public var title: String
    public var replyCount: Int
    public var lastReplyAt: Int64?

    public static let databaseTableName = "threads"

    public init(id: Int64, roomId: Int64, parentMessageId: Int64,
                title: String, replyCount: Int = 0, lastReplyAt: Int64? = nil) {
        self.id = id; self.roomId = roomId; self.parentMessageId = parentMessageId
        self.title = title; self.replyCount = replyCount; self.lastReplyAt = lastReplyAt
    }
}
