import Foundation
import Net
import DB

public final class HttpSpacesRepository: SpacesRepository {
    private let http: HttpClient
    private let dao: SpaceDao

    public init(http: HttpClient, dao: SpaceDao) { self.http = http; self.dao = dao }

    public var spaces: AsyncStream<[Space]> {
        AsyncStream { cont in
            let inner = Task {
                for await rows in dao.observeAll() {
                    cont.yield(rows.map { $0.toDomain })
                }
            }
            cont.onTermination = { @Sendable _ in inner.cancel() }
        }
    }

    public func refresh() async -> Bool {
        do {
            let list = try await http.send(.get("api/spaces/my"), [SpaceDto].self)
            try await dao.upsertAll(list.map(\.toRecord))
            return true
        } catch { return false }
    }

    public func create(name: String, isPublic: Bool) async -> Space? {
        do {
            let req = try HttpRequest.postJson("api/spaces",
                body: CreateReq(name: name, is_public: isPublic))
            let dto = try await http.send(req, SpaceDto.self)
            try await dao.upsertAll([dto.toRecord])
            return dto.toRecord.toDomain
        } catch { return nil }
    }

    public func leave(_ id: Int64) async -> Bool {
        do {
            _ = try await http.send(.delete("api/spaces/\(id)/leave"))
            try await dao.delete(id)
            return true
        } catch { return false }
    }

    private struct CreateReq: Encodable { let name: String; let is_public: Bool }
    private struct SpaceDto: Decodable {
        let id: Int64
        let name: String
        let creator_id: Int64
        let avatar_emoji: String?
        let member_count: Int?
        let is_public: Bool?
        var toRecord: SpaceRecord {
            SpaceRecord(id: id, name: name, ownerId: creator_id,
                        avatarEmoji: avatar_emoji ?? "🌌",
                        memberCount: member_count ?? 0,
                        isPublic: is_public ?? false)
        }
    }
}

private extension SpaceRecord {
    var toDomain: Space {
        Space(id: id, name: name, ownerId: ownerId,
              avatarEmoji: avatarEmoji, memberCount: memberCount, isPublic: isPublic)
    }
}
