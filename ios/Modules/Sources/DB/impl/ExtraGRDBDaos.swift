import Foundation
import GRDB

public final class GRDBSpaceDao: SpaceDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }
    public func observeAll() -> AsyncStream<[SpaceRecord]> {
        GRDBObserve.stream(pool: pool) { try SpaceRecord.order(Column("name").asc).fetchAll($0) }
    }
    public func upsertAll(_ rows: [SpaceRecord]) async throws {
        try await pool.write { db in for var r in rows { try r.save(db) } }
    }
    public func delete(_ id: Int64) async throws {
        _ = try await pool.write { db in try SpaceRecord.deleteOne(db, key: id) }
    }
}

public final class GRDBBotDao: BotDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }
    public func observeMarketplace() -> AsyncStream<[BotRecord]> {
        GRDBObserve.stream(pool: pool) {
            try BotRecord.order(Column("installCount").desc).fetchAll($0)
        }
    }
    public func observeInstalled() -> AsyncStream<[BotRecord]> {
        GRDBObserve.stream(pool: pool) {
            try BotRecord.filter(Column("installed") == true)
                .order(Column("name").asc).fetchAll($0)
        }
    }
    public func upsertAll(_ rows: [BotRecord]) async throws {
        try await pool.write { db in for var r in rows { try r.save(db) } }
    }
    public func setInstalled(_ id: Int64, _ installed: Bool) async throws {
        try await pool.write { db in
            try db.execute(sql: "UPDATE bots SET installed = ? WHERE id = ?",
                           arguments: [installed, id])
        }
    }
}

public final class GRDBThreadDao: ThreadDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }
    public func observeForRoom(_ roomId: Int64) -> AsyncStream<[ThreadRecord]> {
        GRDBObserve.stream(pool: pool) { db in
            try ThreadRecord.filter(Column("roomId") == roomId)
                .order(Column("lastReplyAt").desc)
                .fetchAll(db)
        }
    }
    public func upsertAll(_ rows: [ThreadRecord]) async throws {
        try await pool.write { db in for var r in rows { try r.save(db) } }
    }
}

public final class GRDBChannelFeedDao: ChannelFeedDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }
    public func observeForRoom(_ roomId: Int64) -> AsyncStream<[ChannelFeedRecord]> {
        GRDBObserve.stream(pool: pool) { db in
            try ChannelFeedRecord.filter(Column("roomId") == roomId).fetchAll(db)
        }
    }
    public func upsert(_ row: ChannelFeedRecord) async throws {
        var r = row
        try await pool.write { db in try r.save(db) }
    }
    public func delete(_ id: Int64) async throws {
        _ = try await pool.write { db in try ChannelFeedRecord.deleteOne(db, key: id) }
    }
}

public final class GRDBReactionDao: ReactionDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }
    public func observeForMessage(_ id: Int64) -> AsyncStream<[ReactionRecord]> {
        GRDBObserve.stream(pool: pool) { db in
            try ReactionRecord.filter(Column("messageId") == id).fetchAll(db)
        }
    }
    public func upsert(_ r: ReactionRecord) async throws {
        var row = r
        try await pool.write { db in try row.save(db) }
    }
    public func remove(messageId: Int64, userId: Int64, emoji: String) async throws {
        try await pool.write { db in
            try db.execute(
                sql: "DELETE FROM reactions WHERE messageId=? AND userId=? AND emoji=?",
                arguments: [messageId, userId, emoji],
            )
        }
    }
}

public final class GRDBReadReceiptDao: ReadReceiptDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }
    public func latest(roomId: Int64, userId: Int64) async throws -> Int64? {
        try await pool.read { db in
            try Int64.fetchOne(db,
                sql: "SELECT messageId FROM read_receipts WHERE roomId=? AND userId=? ORDER BY messageId DESC LIMIT 1",
                arguments: [roomId, userId])
        }
    }
    public func upsert(_ r: ReadReceiptRecord) async throws {
        var row = r
        try await pool.write { db in try row.save(db) }
    }
}

/// FTS5-backed search. FTS5 virtual tables keep their own rowid column
/// separate from the physical message table, so we keep them in sync by
/// explicit insert / delete.
public final class GRDBSearchDao: SearchDao {
    private let pool: DatabasePool
    public init(pool: DatabasePool) { self.pool = pool }

    public func index(id: Int64, plaintext: String) async throws {
        try await pool.write { db in
            try db.execute(
                sql: "INSERT OR REPLACE INTO messages_fts(rowid, plaintext) VALUES (?, ?)",
                arguments: [id, plaintext],
            )
        }
    }
    public func unindex(_ id: Int64) async throws {
        try await pool.write { db in
            try db.execute(sql: "DELETE FROM messages_fts WHERE rowid = ?", arguments: [id])
        }
    }
    public func search(_ query: String, limit: Int) async throws -> [MessageRecord] {
        try await pool.read { db in
            try MessageRecord.fetchAll(db, sql: """
                SELECT m.* FROM messages AS m
                JOIN messages_fts AS fts ON fts.rowid = m.id
                WHERE messages_fts MATCH ?
                ORDER BY m.sentAt DESC
                LIMIT ?
                """, arguments: [query, limit])
        }
    }
}

/// Shared helper that bridges any `ValueObservation` to an `AsyncStream`.
enum GRDBObserve {
    static func stream<T: Sendable>(
        pool: DatabasePool,
        _ query: @escaping @Sendable (Database) throws -> T,
    ) -> AsyncStream<T> {
        AsyncStream { cont in
            let obs = ValueObservation.tracking(query)
            let cancellable = obs.start(
                in: pool,
                onError: { _ in cont.finish() },
                onChange: { value in cont.yield(value) },
            )
            cont.onTermination = { @Sendable _ in cancellable.cancel() }
        }
    }
}
