import Foundation
import GRDB

/// Cached symmetric room key. Populated by either the ECIES (private)
/// flow or the Variant-B (public) fast-path. `source` lets us warn
/// when a public→private flip has stranded a cached key.
public struct RoomKeyRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var roomId: Int64
    public var keyHex: String
    public var algorithm: String
    public var source: String         // "ecies" | "public"
    public var createdAt: Int64
    public var rotatedAt: Int64?

    public static let databaseTableName = "room_keys"
    public static let primaryKey = ["roomId"]

    public init(
        roomId: Int64, keyHex: String,
        algorithm: String = "aes-256-gcm",
        source: String, createdAt: Int64,
        rotatedAt: Int64? = nil,
    ) {
        self.roomId = roomId
        self.keyHex = keyHex
        self.algorithm = algorithm
        self.source = source
        self.createdAt = createdAt
        self.rotatedAt = rotatedAt
    }
}
