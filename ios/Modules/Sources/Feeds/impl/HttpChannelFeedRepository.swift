import Foundation
import Net
import DB

public final class HttpChannelFeedRepository: ChannelFeedRepository {
    private let http: HttpClient
    private let dao: ChannelFeedDao

    public init(http: HttpClient, dao: ChannelFeedDao) { self.http = http; self.dao = dao }

    public func observe(_ roomId: Int64) -> AsyncStream<[ChannelFeed]> {
        AsyncStream { cont in
            let inner = Task {
                for await rows in dao.observeForRoom(roomId) { cont.yield(rows.map(\.toDomain)) }
            }
            cont.onTermination = { @Sendable _ in inner.cancel() }
        }
    }

    public func refresh(_ roomId: Int64) async -> Bool {
        do {
            let list = try await http.send(.get("api/rooms/\(roomId)/feeds"), [FeedDto].self)
            for dto in list { try await dao.upsert(dto.toRecord) }
            return true
        } catch { return false }
    }

    public func subscribe(roomId: Int64, url: String, feedType: String) async -> Bool {
        do {
            let req = try HttpRequest.postJson("api/rooms/\(roomId)/feeds",
                body: SubReq(url: url, feed_type: feedType))
            let dto = try await http.send(req, FeedDto.self)
            try await dao.upsert(dto.toRecord)
            return true
        } catch { return false }
    }

    public func unsubscribe(_ feedId: Int64) async -> Bool {
        do {
            _ = try await http.send(.delete("api/feeds/\(feedId)"))
            try await dao.delete(feedId); return true
        } catch { return false }
    }

    private struct SubReq: Encodable { let url: String; let feed_type: String }
    private struct FeedDto: Decodable {
        let id: Int64
        let room_id: Int64
        let feed_type: String
        let url: String
        let last_fetched: Int64?
        let is_active: Bool?
        var toRecord: ChannelFeedRecord {
            ChannelFeedRecord(id: id, roomId: room_id,
                              feedType: feed_type, url: url,
                              lastFetched: last_fetched,
                              isActive: is_active ?? true)
        }
    }
}

private extension ChannelFeedRecord {
    var toDomain: ChannelFeed {
        ChannelFeed(id: id, roomId: roomId, feedType: feedType, url: url,
                    lastFetched: lastFetched, isActive: isActive)
    }
}
