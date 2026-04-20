import Foundation
import Net
import DB
import VortexCrypto
import Identity

/// Creation flow (matches Kotlin `HttpRoomsRepository`):
///   1. Generate random 32-byte AES room key.
///   2. ECIES-encrypt to creator's own X25519 pubkey.
///   3. POST {encrypted_room_key, public_room_key_hex?} → /api/rooms.
///   4. Cache plaintext key locally so next send/receive skip a fetch.
public final class HttpRoomsRepository: RoomsRepository {

    private let http: HttpClient
    private let rooms: RoomDao
    private let roomKeys: RoomKeyDao
    private let aead: Aead
    private let keyAgreement: KeyAgreement
    private let kdf: Kdf
    private let random: SecureRandomProvider
    private let identity: IdentityRepository

    public init(
        http: HttpClient,
        rooms: RoomDao,
        roomKeys: RoomKeyDao,
        aead: Aead,
        keyAgreement: KeyAgreement,
        kdf: Kdf,
        random: SecureRandomProvider,
        identity: IdentityRepository,
    ) {
        self.http = http
        self.rooms = rooms
        self.roomKeys = roomKeys
        self.aead = aead
        self.keyAgreement = keyAgreement
        self.kdf = kdf
        self.random = random
        self.identity = identity
    }

    public func observe() -> AsyncStream<[RoomRecord]> { rooms.observeAll() }

    public func refresh() async -> RefreshResult {
        do {
            let list = try await http.send(.get("api/rooms/my"), [RoomDto].self)
            try await rooms.upsertAll(list.map(\.toRecord))
            return .ok(count: list.count)
        } catch HttpError.status(let code, _) {
            return .error("http_\(code)")
        } catch {
            return .error((error as NSError).localizedDescription)
        }
    }

    public func create(name: String, isPrivate: Bool) async -> RoomResult {
        do {
            let me = try await identity.createOrLoad()
            let roomKey = random.nextBytes(32)

            // ECIES(room_key, my_pubkey). Wire format matches the server's
            // EncryptedRoomKey.ciphertext — nonce(12) || ct || tag(16).
            let eph = keyAgreement.generateKeyPair()
            let shared = try keyAgreement.agree(myPrivate: eph.privateKey, theirPublic: me.x25519.publicKey)
            let aesKey = try kdf.derive(ikm: shared, info: Data("vortex/ecies".utf8), length: 32)
            let ctPacked = try aead.encrypt(key: aesKey, plaintext: roomKey)

            let req = CreateReq(
                name: name,
                is_private: isPrivate,
                encrypted_room_key: EciesDto(
                    ephemeral_pub: Hex.encode(eph.publicKey),
                    ciphertext: Hex.encode(ctPacked),
                ),
                public_room_key_hex: isPrivate ? nil : Hex.encode(roomKey),
            )
            let dto = try await http.send(try HttpRequest.postJson("api/rooms", body: req), RoomDto.self)
            try await rooms.upsert(dto.toRecord)
            try await roomKeys.upsert(RoomKeyRecord(
                roomId: dto.id,
                keyHex: Hex.encode(roomKey),
                algorithm: "aes-256-gcm",
                source: isPrivate ? "ecies" : "public",
                createdAt: Int64(Date().timeIntervalSince1970 * 1000),
            ))
            return .ok(roomId: dto.id)
        } catch HttpError.status(let code, let body) {
            return .error(code: "http_\(code)", message: body)
        } catch {
            return .error(code: "io", message: (error as NSError).localizedDescription)
        }
    }

    public func joinByInvite(_ code: String) async -> RoomResult {
        do {
            let dto = try await http.send(
                HttpRequest(method: .POST, path: "api/rooms/join/\(code)"),
                RoomDto.self,
            )
            try await rooms.upsert(dto.toRecord)
            return .ok(roomId: dto.id)
        } catch HttpError.status(let code, let body) {
            return .error(code: "http_\(code)", message: body)
        } catch {
            return .error(code: "io", message: (error as NSError).localizedDescription)
        }
    }

    public func leave(_ roomId: Int64) async -> Bool {
        do {
            _ = try await http.send(.delete("api/rooms/\(roomId)/leave"))
            try await rooms.delete(roomId)
            return true
        } catch { return false }
    }

    // ── DTOs ───────────────────────────────────────────────────────────

    private struct EciesDto: Codable {
        let ephemeral_pub: String
        let ciphertext: String
    }
    private struct CreateReq: Encodable {
        let name: String
        let is_private: Bool
        let encrypted_room_key: EciesDto
        let public_room_key_hex: String?
    }
    private struct RoomDto: Decodable {
        let id: Int64
        let name: String
        let description: String?
        let invite_code: String
        let is_private: Bool?
        let is_channel: Bool?
        let is_dm: Bool?
        let avatar_emoji: String?
        let member_count: Int?

        var toRecord: RoomRecord {
            RoomRecord(
                id: id, name: name, desc: description ?? "",
                inviteCode: invite_code,
                isPrivate: is_private ?? false,
                isChannel: is_channel ?? false,
                isDm: is_dm ?? false,
                avatarEmoji: avatar_emoji ?? "💬",
                memberCount: member_count ?? 0,
            )
        }
    }
}
