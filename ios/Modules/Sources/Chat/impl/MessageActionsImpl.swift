import Foundation
import Net
import VortexCrypto
import DB
import Keys
import Threads

/// Server-driven message actions. Each method mirrors a `/api/messages/*`
/// endpoint on the node. Local DB updates are optimistic — the server's
/// WS broadcast reconciles the final state in [ChatEngine].
public final class MessageActionsImpl: MessageActions, @unchecked Sendable {
    private let http: HttpClient
    private let aead: Aead
    private let keys: RoomKeyProvider
    private let messages: MessageDao
    private let reactions: ReactionDao
    private let sender: MessageSender
    private let threads: ThreadsRepository

    public init(
        http: HttpClient,
        aead: Aead,
        keys: RoomKeyProvider,
        messages: MessageDao,
        reactions: ReactionDao,
        sender: MessageSender,
        threads: ThreadsRepository,
    ) {
        self.http = http
        self.aead = aead
        self.keys = keys
        self.messages = messages
        self.reactions = reactions
        self.sender = sender
        self.threads = threads
    }

    public func react(messageId: Int64, emoji: String) async -> Bool {
        do {
            // Optimistic — userId = 0 placeholder, server echo overwrites
            // with the real sender_pseudo.
            try await reactions.upsert(ReactionRecord(
                messageId: messageId, userId: 0, emoji: emoji,
                createdAt: Int64(Date().timeIntervalSince1970 * 1000)))
            let req = try HttpRequest.postJson(
                "api/messages/\(messageId)/react",
                body: ReactReq(emoji: emoji))
            _ = try await http.send(req)
            return true
        } catch { return false }
    }

    public func edit(messageId: Int64, newPlaintext: String) async -> Bool {
        guard let existing = try? await messages.byId(messageId) else { return false }
        guard case .ready(let keyHex, _) = await keys.keyFor(existing.roomId) else { return false }
        do {
            let key = try Hex.decode(keyHex)
            let ct  = try aead.encrypt(key: key, plaintext: Data(newPlaintext.utf8))
            let newCtHex = Hex.encode(ct)
            var row = existing
            row.plaintext = newPlaintext
            row.ciphertextHex = newCtHex
            row.editedAt = Int64(Date().timeIntervalSince1970 * 1000)
            try await messages.upsert(row)

            let req = HttpRequest(
                method: .PUT,
                path: "api/messages/\(messageId)",
                body: try JSONEncoder().encode(EditReq(ciphertext: newCtHex)),
                extraHeaders: ["Content-Type": "application/json"],
            )
            _ = try await http.send(req)
            return true
        } catch { return false }
    }

    public func reply(roomId: Int64, replyToMessageId: Int64, plaintext: String) async -> SendOutcome {
        let outcome = await sender.send(roomId: roomId, plaintext: plaintext)
        if case .queued(let localId) = outcome,
           let row = try? await messages.byId(localId) {
            var edited = row
            edited.replyTo = replyToMessageId
            try? await messages.upsert(edited)
        }
        return outcome
    }

    public func delete(messageId: Int64) async -> Bool {
        do {
            try await messages.delete(messageId)
            _ = try await http.send(.delete("api/messages/\(messageId)"))
            return true
        } catch { return false }
    }

    /// Creates a thread rooted at `messageId` via the server's
    /// `/api/rooms/{roomId}/threads` endpoint. Resolves the parent's
    /// roomId from the local cache — both the ECIES flow and the
    /// public-key flow guarantee the message row is already there
    /// before the user can tap "Open thread".
    public func openThread(messageId: Int64, title: String?) async -> Threads.Thread? {
        guard let parent = try? await messages.byId(messageId) else { return nil }
        let headline = title
            ?? parent.plaintext.map { String($0.prefix(40)) }
            ?? "Thread"
        return await threads.create(
            roomId: parent.roomId,
            parentMessageId: messageId,
            title: headline,
        )
    }

    private struct ReactReq: Encodable { let emoji: String }
    private struct EditReq: Encodable  { let ciphertext: String }
}
