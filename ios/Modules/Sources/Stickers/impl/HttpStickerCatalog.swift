import Foundation
import Net

public final class HttpStickerCatalog: StickerCatalog {
    private let http: HttpClient
    private let bridge = StickersBridge()

    public init(http: HttpClient) { self.http = http }

    public var favorites: AsyncStream<[StickerPack]> { bridge.stream() }

    public func refresh() async {
        do {
            let resp = try await http.send(.get("api/stickers/favorites"), FavoritesResp.self)
            bridge.publish(resp.packs.map {
                StickerPack(id: $0.id, name: $0.name, coverUrl: $0.cover_url, stickerCount: $0.count)
            })
        } catch { /* keep last */ }
    }

    public func addPack(_ id: String) async -> Bool {
        do {
            _ = try await http.send(HttpRequest(method: .POST, path: "api/stickers/packs/\(id)/subscribe"))
            await refresh()
            return true
        } catch { return false }
    }

    public func removePack(_ id: String) async -> Bool {
        do {
            _ = try await http.send(.delete("api/stickers/packs/\(id)/subscribe"))
            await refresh()
            return true
        } catch { return false }
    }

    private struct PackDto: Decodable {
        let id: String
        let name: String
        let cover_url: String
        let count: Int
    }
    private struct FavoritesResp: Decodable { let packs: [PackDto] }
}

/// Trivial fan-out so multiple screens observing `favorites` get the
/// same snapshot (the catalog is a single list per user).
private final class StickersBridge: @unchecked Sendable {
    private let lock = NSLock()
    private var subs: [UUID: AsyncStream<[StickerPack]>.Continuation] = [:]
    private var last: [StickerPack] = []

    func publish(_ v: [StickerPack]) {
        lock.lock(); last = v; let copy = subs.values; lock.unlock()
        for c in copy { c.yield(v) }
    }
    func stream() -> AsyncStream<[StickerPack]> {
        AsyncStream { cont in
            lock.lock(); cont.yield(last); let id = UUID(); subs[id] = cont; lock.unlock()
            cont.onTermination = { @Sendable _ in
                self.lock.lock(); self.subs.removeValue(forKey: id); self.lock.unlock()
            }
        }
    }
}
