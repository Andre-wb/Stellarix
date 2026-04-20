import Foundation

/// DAO protocols — one per aggregate, matching the Kotlin
/// `*Dao` split. Feature repositories depend on these, never on GRDB
/// directly, so a migration to e.g. Core Data or FMDB is local.
public protocol RoomDao: Sendable {
    func all() async throws -> [RoomRecord]
    func byId(_ id: Int64) async throws -> RoomRecord?
    func upsert(_ room: RoomRecord) async throws
    func upsertAll(_ rooms: [RoomRecord]) async throws
    func markRead(_ id: Int64) async throws
    func delete(_ id: Int64) async throws
    func observeAll() -> AsyncStream<[RoomRecord]>
}

public protocol MessageDao: Sendable {
    func inRoom(_ roomId: Int64) async throws -> [MessageRecord]
    func byId(_ id: Int64) async throws -> MessageRecord?
    func undecrypted(_ roomId: Int64) async throws -> [MessageRecord]
    func upsert(_ msg: MessageRecord) async throws
    func delete(_ id: Int64) async throws
    func observeRoom(_ roomId: Int64) -> AsyncStream<[MessageRecord]>
}

public protocol RoomKeyDao: Sendable {
    func forRoom(_ roomId: Int64) async throws -> RoomKeyRecord?
    func upsert(_ k: RoomKeyRecord) async throws
    func delete(_ roomId: Int64) async throws
}
