import Foundation
import Net

public final class HttpMirrorDirectory: MirrorDirectory {
    private let http: HttpClient
    private let bridge = Bridge()

    public init(http: HttpClient) { self.http = http }

    public var mirrors: AsyncStream<[Mirror]> { bridge.stream() }

    public func refresh() async -> Bool {
        do {
            let resp = try await http.send(.get("v1/mirrors"), MirrorListResp.self)
            bridge.publish(resp.mirrors.map {
                Mirror(id: $0.id, url: $0.url, kind: $0.kind,
                       lastSeenEpoch: $0.last_seen, healthy: $0.healthy)
            })
            return true
        } catch { return false }
    }

    public func probe(_ mirrorId: String) async -> Bool {
        // Probe is a lightweight network poke; it's a status signal, not
        // a retry path.  Lives here rather than in NodeDirectory because
        // mirrors are already authorised by the primary controller.
        // Always report true for now — full health check wires in later.
        true
    }

    private struct MirrorDto: Decodable {
        let id: String
        let url: String
        let kind: String
        let last_seen: Int64?
        let healthy: Bool
    }
    private struct MirrorListResp: Decodable { let mirrors: [MirrorDto] }

    private final class Bridge: @unchecked Sendable {
        private let lock = NSLock()
        private var subs: [UUID: AsyncStream<[Mirror]>.Continuation] = [:]
        private var last: [Mirror] = []
        func publish(_ v: [Mirror]) {
            lock.lock(); last = v; let copy = subs.values; lock.unlock()
            for c in copy { c.yield(v) }
        }
        func stream() -> AsyncStream<[Mirror]> {
            AsyncStream { cont in
                lock.lock(); cont.yield(last); let id = UUID(); subs[id] = cont; lock.unlock()
                cont.onTermination = { @Sendable _ in
                    self.lock.lock(); self.subs.removeValue(forKey: id); self.lock.unlock()
                }
            }
        }
    }
}
