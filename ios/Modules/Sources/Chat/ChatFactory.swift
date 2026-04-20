import Foundation
import VortexCrypto
import DB
import Keys
import WS
import Net
import Search
import Threads

public struct ChatFactory {
    public let sender: MessageSender
    public let incoming: IncomingMessages
    public let actions: MessageActions

    public init(
        ws: WsClient,
        crypto: VortexCryptoFactory,
        keys: RoomKeyProvider,
        db: DBFactory,
        http: HttpClient,
        searchRepo: SearchRepository,
        threads: ThreadsRepository,
    ) {
        // ChatEngine wires FTS indexing via SearchRepository so every
        // decrypted plaintext becomes searchable without extra hooks.
        let indexingDao = IndexingMessageDao(inner: db.messages, search: searchRepo)
        let engine = ChatEngine(ws: ws, aead: crypto.aead, keys: keys, dao: indexingDao)
        self.sender = engine
        self.incoming = engine
        self.actions = MessageActionsImpl(
            http: http,
            aead: crypto.aead,
            keys: keys,
            messages: db.messages,
            reactions: db.reactions,
            sender: engine,
            threads: threads,
        )
    }
}

/// Decorator over MessageDao that forwards plaintext writes to the
/// SearchRepository. Keeps ChatEngine unaware of search.
private final class IndexingMessageDao: MessageDao, @unchecked Sendable {
    private let inner: MessageDao
    private let search: SearchRepository

    init(inner: MessageDao, search: SearchRepository) {
        self.inner = inner; self.search = search
    }

    func inRoom(_ roomId: Int64) async throws -> [MessageRecord] {
        try await inner.inRoom(roomId)
    }
    func byId(_ id: Int64) async throws -> MessageRecord? {
        try await inner.byId(id)
    }
    func undecrypted(_ roomId: Int64) async throws -> [MessageRecord] {
        try await inner.undecrypted(roomId)
    }
    func upsert(_ msg: MessageRecord) async throws {
        try await inner.upsert(msg)
        if let text = msg.plaintext, !text.isEmpty {
            await search.index(id: msg.id, plaintext: text)
        }
    }
    func delete(_ id: Int64) async throws {
        try await inner.delete(id)
        await search.unindex(id)
    }
    func observeRoom(_ roomId: Int64) -> AsyncStream<[MessageRecord]> {
        inner.observeRoom(roomId)
    }
}
