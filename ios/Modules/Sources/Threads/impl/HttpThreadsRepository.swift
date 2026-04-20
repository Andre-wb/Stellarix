import Foundation
import Net
import DB

public final class HttpThreadsRepository: ThreadsRepository {
    private let http: HttpClient
    private let dao: ThreadDao

    public init(http: HttpClient, dao: ThreadDao) { self.http = http; self.dao = dao }

    public func observeForRoom(_ roomId: Int64) -> AsyncStream<[Thread]> {
        AsyncStream { cont in
            let inner = Task {
                for await rows in dao.observeForRoom(roomId) { cont.yield(rows.map(\.toDomain)) }
            }
            cont.onTermination = { @Sendable _ in inner.cancel() }
        }
    }

    public func refresh(_ roomId: Int64) async -> Bool {
        do {
            let list = try await http.send(.get("api/rooms/\(roomId)/threads"), [ThreadDto].self)
            try await dao.upsertAll(list.map(\.toRecord))
            return true
        } catch { return false }
    }

    public func create(roomId: Int64, parentMessageId: Int64, title: String) async -> Thread? {
        do {
            let req = try HttpRequest.postJson("api/rooms/\(roomId)/threads",
                body: CreateReq(parent_message_id: parentMessageId, title: title))
            let dto = try await http.send(req, ThreadDto.self)
            try await dao.upsertAll([dto.toRecord])
            return dto.toRecord.toDomain
        } catch { return nil }
    }

    private struct CreateReq: Encodable {
        let parent_message_id: Int64
        let title: String
    }
    private struct ThreadDto: Decodable {
        let id: Int64
        let room_id: Int64
        let parent_message_id: Int64
        let title: String
        let reply_count: Int?
        let last_reply_at: Int64?
        var toRecord: ThreadRecord {
            ThreadRecord(id: id, roomId: room_id, parentMessageId: parent_message_id,
                         title: title, replyCount: reply_count ?? 0,
                         lastReplyAt: last_reply_at)
        }
    }
}

private extension ThreadRecord {
    var toDomain: Thread {
        Thread(id: id, roomId: roomId, parentMessageId: parentMessageId,
               title: title, replyCount: replyCount, lastReplyAt: lastReplyAt)
    }
}
