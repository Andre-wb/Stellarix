import Foundation

public struct DBFactory {
    public let db: VortexDatabase
    public let rooms: RoomDao
    public let messages: MessageDao
    public let roomKeys: RoomKeyDao
    public let spaces: SpaceDao
    public let bots: BotDao
    public let threads: ThreadDao
    public let feeds: ChannelFeedDao
    public let reactions: ReactionDao
    public let receipts: ReadReceiptDao
    public let search: SearchDao

    public init(storage: VortexDatabase.Storage = .onDisk) throws {
        let db = try VortexDatabase(storage: storage)
        self.db = db
        self.rooms    = GRDBRoomDao(pool: db.pool)
        self.messages = GRDBMessageDao(pool: db.pool)
        self.roomKeys = GRDBRoomKeyDao(pool: db.pool)
        self.spaces   = GRDBSpaceDao(pool: db.pool)
        self.bots     = GRDBBotDao(pool: db.pool)
        self.threads  = GRDBThreadDao(pool: db.pool)
        self.feeds    = GRDBChannelFeedDao(pool: db.pool)
        self.reactions = GRDBReactionDao(pool: db.pool)
        self.receipts = GRDBReadReceiptDao(pool: db.pool)
        self.search   = GRDBSearchDao(pool: db.pool)
    }
}
