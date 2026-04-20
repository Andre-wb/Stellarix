import Foundation
import Net
import DB

public final class HttpBotsRepository: BotsRepository {
    private let http: HttpClient
    private let dao: BotDao

    public init(http: HttpClient, dao: BotDao) { self.http = http; self.dao = dao }

    public var marketplace: AsyncStream<[Bot]> { bridge(dao.observeMarketplace()) }
    public var installed:   AsyncStream<[Bot]> { bridge(dao.observeInstalled()) }

    public func refreshMarketplace() async -> Bool {
        do {
            let list = try await http.send(.get("api/bots/marketplace"), [BotDto].self)
            try await dao.upsertAll(list.map(\.toRecord))
            return true
        } catch { return false }
    }

    public func install(_ id: Int64) async -> Bool {
        do {
            _ = try await http.send(HttpRequest(method: .POST, path: "api/bots/\(id)/install"))
            try await dao.setInstalled(id, true); return true
        } catch { return false }
    }

    public func uninstall(_ id: Int64) async -> Bool {
        do {
            _ = try await http.send(.delete("api/bots/\(id)/install"))
            try await dao.setInstalled(id, false); return true
        } catch { return false }
    }

    private func bridge(_ src: AsyncStream<[BotRecord]>) -> AsyncStream<[Bot]> {
        AsyncStream { cont in
            let inner = Task {
                for await rows in src { cont.yield(rows.map(\.toDomain)) }
            }
            cont.onTermination = { @Sendable _ in inner.cancel() }
        }
    }

    private struct BotDto: Decodable {
        let id: Int64
        let name: String
        let author: String?
        let short_description: String?
        let avatar_url: String?
        let installed: Bool?
        let rating: Double?
        let install_count: Int64?
        var toRecord: BotRecord {
            BotRecord(id: id, name: name, author: author ?? "",
                      shortDescription: short_description ?? "",
                      avatarUrl: avatar_url,
                      installed: installed ?? false,
                      rating: rating ?? 0,
                      installCount: install_count ?? 0)
        }
    }
}

private extension BotRecord {
    var toDomain: Bot {
        Bot(id: id, name: name, author: author,
            shortDescription: shortDescription, avatarUrl: avatarUrl,
            installed: installed, rating: rating, installCount: installCount)
    }
}
