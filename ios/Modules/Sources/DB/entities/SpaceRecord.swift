import Foundation
import GRDB

public struct SpaceRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var id: Int64
    public var name: String
    public var ownerId: Int64
    public var avatarEmoji: String
    public var memberCount: Int
    public var isPublic: Bool

    public static let databaseTableName = "spaces"

    public init(id: Int64, name: String, ownerId: Int64,
                avatarEmoji: String = "🌌", memberCount: Int = 0, isPublic: Bool = false) {
        self.id = id; self.name = name; self.ownerId = ownerId
        self.avatarEmoji = avatarEmoji; self.memberCount = memberCount; self.isPublic = isPublic
    }
}
