import Foundation
import GRDB

/// Local mirror of a server-side room.
///
/// `isPrivate == false` is what switches the client between the ECIES
/// per-member flow and the Variant-B plaintext-key fast path.
public struct RoomRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var id: Int64
    public var name: String
    public var desc: String
    public var inviteCode: String
    public var isPrivate: Bool
    public var isChannel: Bool
    public var isDm: Bool
    public var avatarEmoji: String
    public var memberCount: Int
    public var unreadCount: Int
    public var lastMessageAt: Int64?   // epoch millis, null = no messages yet

    public static let databaseTableName = "rooms"

    public init(
        id: Int64, name: String, desc: String = "",
        inviteCode: String, isPrivate: Bool = false,
        isChannel: Bool = false, isDm: Bool = false,
        avatarEmoji: String = "💬",
        memberCount: Int = 0, unreadCount: Int = 0,
        lastMessageAt: Int64? = nil,
    ) {
        self.id = id
        self.name = name
        self.desc = desc
        self.inviteCode = inviteCode
        self.isPrivate = isPrivate
        self.isChannel = isChannel
        self.isDm = isDm
        self.avatarEmoji = avatarEmoji
        self.memberCount = memberCount
        self.unreadCount = unreadCount
        self.lastMessageAt = lastMessageAt
    }
}
