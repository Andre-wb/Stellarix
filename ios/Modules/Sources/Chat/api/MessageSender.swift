import Foundation
import DB

/// Send path. Returns a send outcome once the frame has been queued on
/// the WS — delivery receipts are a separate concern (Wave 13+).
public protocol MessageSender: Sendable {
    func send(roomId: Int64, plaintext: String) async -> SendOutcome
}

public enum SendOutcome: Sendable, Equatable {
    case queued(localId: Int64)
    case error(String)
}

/// Receive path — server-pushed message events, already decrypted and
/// persisted locally.
public protocol IncomingMessages: Sendable {
    func messagesIn(_ roomId: Int64) -> AsyncStream<[MessageRecord]>
}
