import Foundation
import Net

/// REST-backed [Drafts] with a small in-memory cache keyed by roomId.
/// Writes debounce on the caller side; this just forwards.
public actor HttpDrafts: Drafts {
    private let http: HttpClient
    private var cache: [Int64: String] = [:]

    public init(http: HttpClient) { self.http = http }

    private struct DraftBody: Codable { let text: String }
    private struct DraftResponse: Codable { let text: String? }

    public func get(roomId: Int64) async -> String? {
        if let cached = cache[roomId] { return cached.isEmpty ? nil : cached }
        let req = HttpRequest.get("/api/rooms/\(roomId)/draft")
        if let resp = try? await http.send(req, DraftResponse.self) {
            let t = resp.text ?? ""
            cache[roomId] = t
            return t.isEmpty ? nil : t
        }
        return nil
    }

    public func set(roomId: Int64, text: String) async {
        let trimmed = text
        cache[roomId] = trimmed
        guard !trimmed.isEmpty else {
            await clear(roomId: roomId)
            return
        }
        guard var req = try? HttpRequest.postJson("/api/rooms/\(roomId)/draft", body: DraftBody(text: trimmed)) else { return }
        req.method = .PUT
        _ = try? await http.send(req, DraftResponse.self)
    }

    public func clear(roomId: Int64) async {
        cache[roomId] = ""
        let req = HttpRequest.delete("/api/rooms/\(roomId)/draft")
        _ = try? await http.send(req)
    }
}
