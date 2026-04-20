import Foundation
import GRDB

/// Sets up the GRDB database pool + schema migrator. Later waves add
/// more tables by appending migration steps — never by editing past ones.
public final class VortexDatabase: @unchecked Sendable {
    public let pool: DatabasePool

    public init(storage: Storage = .onDisk) throws {
        switch storage {
        case .onDisk:
            let dir = try FileManager.default.url(
                for: .applicationSupportDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: true,
            )
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let path = dir.appendingPathComponent("vortex.sqlite").path
            self.pool = try DatabasePool(path: path)
        case .inMemory:
            self.pool = try DatabasePool(path: ":memory:")
        }
        try Self.migrator().migrate(pool)
    }

    public enum Storage { case onDisk, inMemory }

    private static func migrator() -> DatabaseMigrator {
        var m = DatabaseMigrator()
        m.registerMigration("v1_core") { db in
            try db.create(table: "rooms") { t in
                t.column("id", .integer).primaryKey()
                t.column("name", .text).notNull()
                t.column("desc", .text).notNull().defaults(to: "")
                t.column("inviteCode", .text).notNull()
                t.column("isPrivate", .boolean).notNull().defaults(to: false)
                t.column("isChannel", .boolean).notNull().defaults(to: false)
                t.column("isDm", .boolean).notNull().defaults(to: false)
                t.column("avatarEmoji", .text).notNull().defaults(to: "💬")
                t.column("memberCount", .integer).notNull().defaults(to: 0)
                t.column("unreadCount", .integer).notNull().defaults(to: 0)
                t.column("lastMessageAt", .integer)
            }
            try db.create(table: "messages") { t in
                t.column("id", .integer).primaryKey()
                t.column("roomId", .integer).notNull()
                    .references("rooms", onDelete: .cascade)
                t.column("senderId", .integer)
                t.column("senderUsername", .text)
                t.column("msgType", .text).notNull().defaults(to: "text")
                t.column("plaintext", .text)
                t.column("ciphertextHex", .text).notNull()
                t.column("sentAt", .integer).notNull()
                t.column("editedAt", .integer)
                t.column("replyTo", .integer)
            }
            try db.create(indexOn: "messages", columns: ["roomId"])
            try db.create(indexOn: "messages", columns: ["sentAt"])

            try db.create(table: "room_keys") { t in
                t.column("roomId", .integer).primaryKey()
                    .references("rooms", onDelete: .cascade)
                t.column("keyHex", .text).notNull()
                t.column("algorithm", .text).notNull().defaults(to: "aes-256-gcm")
                t.column("source", .text).notNull()
                t.column("createdAt", .integer).notNull()
                t.column("rotatedAt", .integer)
            }
        }
        m.registerMigration("v2_features") { db in
            try db.create(table: "spaces") { t in
                t.column("id", .integer).primaryKey()
                t.column("name", .text).notNull()
                t.column("ownerId", .integer).notNull()
                t.column("avatarEmoji", .text).notNull().defaults(to: "🌌")
                t.column("memberCount", .integer).notNull().defaults(to: 0)
                t.column("isPublic", .boolean).notNull().defaults(to: false)
            }
            try db.create(table: "bots") { t in
                t.column("id", .integer).primaryKey()
                t.column("name", .text).notNull()
                t.column("author", .text).notNull().defaults(to: "")
                t.column("shortDescription", .text).notNull().defaults(to: "")
                t.column("avatarUrl", .text)
                t.column("installed", .boolean).notNull().defaults(to: false)
                t.column("rating", .double).notNull().defaults(to: 0)
                t.column("installCount", .integer).notNull().defaults(to: 0)
            }
            try db.create(table: "threads") { t in
                t.column("id", .integer).primaryKey()
                t.column("roomId", .integer).notNull()
                    .references("rooms", onDelete: .cascade)
                t.column("parentMessageId", .integer).notNull()
                t.column("title", .text).notNull()
                t.column("replyCount", .integer).notNull().defaults(to: 0)
                t.column("lastReplyAt", .integer)
            }
            try db.create(indexOn: "threads", columns: ["roomId"])

            try db.create(table: "channel_feeds") { t in
                t.column("id", .integer).primaryKey()
                t.column("roomId", .integer).notNull()
                    .references("rooms", onDelete: .cascade)
                t.column("feedType", .text).notNull().defaults(to: "rss")
                t.column("url", .text).notNull()
                t.column("lastFetched", .integer)
                t.column("isActive", .boolean).notNull().defaults(to: true)
            }

            try db.create(table: "reactions") { t in
                t.column("messageId", .integer).notNull()
                    .references("messages", onDelete: .cascade)
                t.column("userId", .integer).notNull()
                t.column("emoji", .text).notNull()
                t.column("createdAt", .integer).notNull()
                t.primaryKey(["messageId", "userId", "emoji"])
            }
            try db.create(indexOn: "reactions", columns: ["messageId"])

            try db.create(table: "read_receipts") { t in
                t.column("roomId", .integer).notNull()
                t.column("userId", .integer).notNull()
                t.column("messageId", .integer).notNull()
                t.column("readAt", .integer).notNull()
                t.primaryKey(["roomId", "userId"])
            }

            // FTS5 virtual table over decrypted message plaintext.
            // Chat's SearchRepository fills this on send/receive.
            try db.execute(sql: """
                CREATE VIRTUAL TABLE messages_fts USING fts5(
                    plaintext,
                    content='messages',
                    content_rowid='id'
                )
                """)
        }
        return m
    }
}
