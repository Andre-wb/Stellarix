import Foundation
import Net

public actor HttpScheduled: ScheduledMessages {
    private let http: HttpClient
    public init(http: HttpClient) { self.http = http }

    private struct Wrap: Codable { let items: [ScheduledMessage] }
    private struct AddBody: Codable { let room_id: Int64; let ciphertext_b64: String; let send_at: Int64 }
    private struct EditBody: Codable { let ciphertext_b64: String; let send_at: Int64? }

    public func list(roomId: Int64) async -> [ScheduledMessage] {
        let req = HttpRequest.get("/api/scheduled", query: [URLQueryItem(name: "room_id", value: "\(roomId)")])
        return (try? await http.send(req, Wrap.self).items) ?? []
    }

    public func schedule(roomId: Int64, ciphertextB64: String, sendAt: Int64) async -> ScheduledMessage? {
        guard let req = try? HttpRequest.postJson("/api/scheduled",
            body: AddBody(room_id: roomId, ciphertext_b64: ciphertextB64, send_at: sendAt)) else { return nil }
        return try? await http.send(req, ScheduledMessage.self)
    }

    public func cancel(id: Int64) async {
        let req = HttpRequest.delete("/api/scheduled/\(id)")
        _ = try? await http.send(req)
    }

    public func edit(id: Int64, newCiphertextB64: String, newSendAt: Int64?) async -> ScheduledMessage? {
        guard var req = try? HttpRequest.postJson("/api/scheduled/\(id)",
            body: EditBody(ciphertext_b64: newCiphertextB64, send_at: newSendAt)) else { return nil }
        req.method = .PATCH
        return try? await http.send(req, ScheduledMessage.self)
    }
}
