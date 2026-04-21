import Foundation

public struct ScheduledMessage: Sendable, Codable, Hashable, Identifiable {
    public let id: Int64
    public let roomId: Int64
    public let ciphertextB64: String   // same AEAD envelope as Chat.send
    public let sendAt: Int64           // unix ms UTC
    public let createdAt: Int64

    public init(id: Int64, roomId: Int64, ciphertextB64: String, sendAt: Int64, createdAt: Int64) {
        self.id = id; self.roomId = roomId; self.ciphertextB64 = ciphertextB64
        self.sendAt = sendAt; self.createdAt = createdAt
    }
}

/// Server-side delayed send — the ciphertext is stored until `sendAt`,
/// then committed into the room's message log. Cancellation only works
/// before the fire time.
public protocol ScheduledMessages: Sendable {
    func list(roomId: Int64) async -> [ScheduledMessage]
    func schedule(roomId: Int64, ciphertextB64: String, sendAt: Int64) async -> ScheduledMessage?
    func cancel(id: Int64) async
    func edit(id: Int64, newCiphertextB64: String, newSendAt: Int64?) async -> ScheduledMessage?
}
