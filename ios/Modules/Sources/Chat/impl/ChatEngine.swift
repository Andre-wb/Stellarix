import Foundation
import VortexCrypto
import DB
import Keys
import WS

/// End-to-end chat engine.
///
/// Mirrors the Android `ChatEngine`:
///   * send → AEAD encrypt with room key → WS frame + local DB row
///   * receive → decode JSON → decrypt → DB upsert
///   * on `public_room_key_updated` / `room_key` re-decrypts stored
///     messages that were previously pending a key.
public final class ChatEngine: MessageSender, IncomingMessages, @unchecked Sendable {
    private let ws: WsClient
    private let aead: Aead
    private let keys: RoomKeyProvider
    private let dao: MessageDao
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    private let runTask: Task<Void, Never>

    public init(ws: WsClient, aead: Aead, keys: RoomKeyProvider, dao: MessageDao) {
        self.ws = ws
        self.aead = aead
        self.keys = keys
        self.dao = dao
        // Must capture the stream *before* calling `start()` so we don't
        // race with reconnect emitting the first frame.
        let incoming = ws.incoming
        self.runTask = Task { [aead, keys, dao] in
            await ChatEngine.observeIncoming(incoming: incoming, aead: aead, keys: keys, dao: dao)
        }
    }

    public func messagesIn(_ roomId: Int64) -> AsyncStream<[MessageRecord]> {
        dao.observeRoom(roomId)
    }

    public func send(roomId: Int64, plaintext: String) async -> SendOutcome {
        let keyHex: String
        switch await keys.keyFor(roomId) {
        case .ready(let hex, _): keyHex = hex
        case .pending(let r):    return .error("key_pending:\(r)")
        case .error(let r):      return .error(r)
        }
        do {
            let key = try Hex.decode(keyHex)
            let packed = try aead.encrypt(key: key, plaintext: Data(plaintext.utf8))
            let ctHex = Hex.encode(packed)
            let localId = Int64.random(in: 1...Int64.max)
            try await dao.upsert(MessageRecord(
                id: localId, roomId: roomId,
                plaintext: plaintext, ciphertextHex: ctHex,
                sentAt: Int64(Date().timeIntervalSince1970 * 1000),
            ))
            let frame = OutFrame(action: "send_message", room_id: roomId, ciphertext: ctHex)
            if let json = try? encoder.encode(frame), let s = String(data: json, encoding: .utf8) {
                await ws.send(s)
            }
            return .queued(localId: localId)
        } catch {
            return .error((error as NSError).localizedDescription)
        }
    }

    // ── incoming loop ──────────────────────────────────────────────────

    private static func observeIncoming(
        incoming: AsyncStream<String>,
        aead: Aead,
        keys: RoomKeyProvider,
        dao: MessageDao,
    ) async {
        let decoder = JSONDecoder()
        for await text in incoming {
            guard let data = text.data(using: .utf8) else { continue }
            guard let generic = try? decoder.decode(GenericFrame.self, from: data) else { continue }
            switch generic.type {
            case "peer_message":
                await onPeerMessage(data, aead: aead, keys: keys, dao: dao)
            case "public_room_key_updated", "room_key", "room_key_rotated":
                if let rid = generic.room_id { await retryUndecrypted(rid, aead: aead, keys: keys, dao: dao) }
            default: break
            }
        }
    }

    private static func onPeerMessage(
        _ data: Data, aead: Aead, keys: RoomKeyProvider, dao: MessageDao,
    ) async {
        guard let m = try? JSONDecoder().decode(PeerMessage.self, from: data) else { return }
        let plaintext = await tryDecrypt(roomId: m.room_id, ctHex: m.ciphertext, aead: aead, keys: keys)
        let row = MessageRecord(
            id: m.msg_id ?? Int64(Date().timeIntervalSince1970 * 1_000_000),
            roomId: m.room_id,
            senderUsername: m.sender,
            plaintext: plaintext,
            ciphertextHex: m.ciphertext,
            sentAt: Int64(Date().timeIntervalSince1970 * 1000),
        )
        try? await dao.upsert(row)
    }

    private static func retryUndecrypted(
        _ roomId: Int64, aead: Aead, keys: RoomKeyProvider, dao: MessageDao,
    ) async {
        guard let pending = try? await dao.undecrypted(roomId), !pending.isEmpty else { return }
        for var row in pending {
            guard let plaintext = await tryDecrypt(
                roomId: roomId, ctHex: row.ciphertextHex, aead: aead, keys: keys,
            ) else { continue }
            row.plaintext = plaintext
            try? await dao.upsert(row)
        }
    }

    private static func tryDecrypt(
        roomId: Int64, ctHex: String, aead: Aead, keys: RoomKeyProvider,
    ) async -> String? {
        guard case .ready(let keyHex, _) = await keys.keyFor(roomId) else { return nil }
        guard let key = try? Hex.decode(keyHex),
              let packed = try? Hex.decode(ctHex),
              let plain = try? aead.decrypt(key: key, packed: packed)
        else { return nil }
        return String(data: plain, encoding: .utf8)
    }

    // ── DTOs ───────────────────────────────────────────────────────────

    private struct OutFrame: Codable {
        let action: String
        let room_id: Int64
        let ciphertext: String
    }
    private struct GenericFrame: Decodable {
        let type: String?
        let room_id: Int64?
    }
    private struct PeerMessage: Decodable {
        let room_id: Int64
        let ciphertext: String
        let sender: String?
        let msg_id: Int64?
    }
}
