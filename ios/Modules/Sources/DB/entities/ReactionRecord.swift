import Foundation
import GRDB

public struct ReactionRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var messageId: Int64
    public var userId: Int64
    public var emoji: String
    public var createdAt: Int64

    public static let databaseTableName = "reactions"
    public static let primaryKey = ["messageId", "userId", "emoji"]
}

public struct ReadReceiptRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var roomId: Int64
    public var userId: Int64
    public var messageId: Int64
    public var readAt: Int64

    public static let databaseTableName = "read_receipts"
    public static let primaryKey = ["roomId", "userId"]
}
