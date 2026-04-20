import Foundation
import GRDB

/// GRDB-backed DAO implementations. Each observer emits via an
/// `AsyncStream` so feature view models don't need Combine.
public final class GRDBRoomDao: RoomDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }

    public func all() async throws -> [RoomRecord] {
        try await pool.read { db in try RoomRecord.fetchAll(db) }
    }
    public func byId(_ id: Int64) async throws -> RoomRecord? {
        try await pool.read { db in try RoomRecord.fetchOne(db, key: id) }
    }
    public func upsert(_ room: RoomRecord) async throws {
        var r = room
        try await pool.write { db in try r.save(db) }
    }
    public func upsertAll(_ rooms: [RoomRecord]) async throws {
        try await pool.write { db in
            for var r in rooms { try r.save(db) }
        }
    }
    public func markRead(_ id: Int64) async throws {
        try await pool.write { db in
            try db.execute(sql: "UPDATE rooms SET unreadCount = 0 WHERE id = ?", arguments: [id])
        }
    }
    public func delete(_ id: Int64) async throws {
        _ = try await pool.write { db in try RoomRecord.deleteOne(db, key: id) }
    }
    public func observeAll() -> AsyncStream<[RoomRecord]> {
        observe(ValueObservation.tracking { db in
            try RoomRecord
                .order(Column("lastMessageAt").desc, Column("name").asc)
                .fetchAll(db)
        })
    }

    private func observe(_ obs: ValueObservation<ValueReducers.Fetch<[RoomRecord]>>) -> AsyncStream<[RoomRecord]> {
        AsyncStream { cont in
            let cancellable = obs.start(
                in: pool,
                onError: { _ in cont.finish() },
                onChange: { rows in cont.yield(rows) },
            )
            cont.onTermination = { @Sendable _ in cancellable.cancel() }
        }
    }
}

public final class GRDBMessageDao: MessageDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }

    public func inRoom(_ roomId: Int64) async throws -> [MessageRecord] {
        try await pool.read { db in
            try MessageRecord
                .filter(Column("roomId") == roomId)
                .order(Column("sentAt").asc)
                .fetchAll(db)
        }
    }
    public func byId(_ id: Int64) async throws -> MessageRecord? {
        try await pool.read { db in try MessageRecord.fetchOne(db, key: id) }
    }
    public func undecrypted(_ roomId: Int64) async throws -> [MessageRecord] {
        try await pool.read { db in
            try MessageRecord
                .filter(Column("roomId") == roomId && Column("plaintext") == nil)
                .fetchAll(db)
        }
    }
    public func upsert(_ msg: MessageRecord) async throws {
        var m = msg
        try await pool.write { db in try m.save(db) }
    }
    public func delete(_ id: Int64) async throws {
        _ = try await pool.write { db in try MessageRecord.deleteOne(db, key: id) }
    }
    public func observeRoom(_ roomId: Int64) -> AsyncStream<[MessageRecord]> {
        let obs = ValueObservation.tracking { db in
            try MessageRecord
                .filter(Column("roomId") == roomId)
                .order(Column("sentAt").asc)
                .fetchAll(db)
        }
        return AsyncStream { cont in
            let cancellable = obs.start(
                in: pool,
                onError: { _ in cont.finish() },
                onChange: { rows in cont.yield(rows) },
            )
            cont.onTermination = { @Sendable _ in cancellable.cancel() }
        }
    }
}

public final class GRDBRoomKeyDao: RoomKeyDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }

    public func forRoom(_ roomId: Int64) async throws -> RoomKeyRecord? {
        try await pool.read { db in try RoomKeyRecord.fetchOne(db, key: roomId) }
    }
    public func upsert(_ k: RoomKeyRecord) async throws {
        var row = k
        try await pool.write { db in try row.save(db) }
    }
    public func delete(_ roomId: Int64) async throws {
        _ = try await pool.write { db in try RoomKeyRecord.deleteOne(db, key: roomId) }
    }
}
