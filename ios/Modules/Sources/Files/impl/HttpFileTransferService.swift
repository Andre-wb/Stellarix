import Foundation
import Net
import VortexCrypto
import Keys

/// Single-shot encrypt+upload for small files; switches automatically
/// to [ResumableUpload] above 10 MiB so memory stays bounded.
public final class HttpFileTransferService: FileTransferService {
    private let http: HttpClient
    private let aead: Aead
    private let keys: RoomKeyProvider
    private let resumable: ResumableUpload

    private let singleShotMax: Int64 = 10 * 1024 * 1024

    public init(http: HttpClient, aead: Aead, keys: RoomKeyProvider, resumable: ResumableUpload) {
        self.http = http
        self.aead = aead
        self.keys = keys
        self.resumable = resumable
    }

    public func upload(roomId: Int64, filename: String, data: Data) -> AsyncStream<TransferProgress> {
        // Anything over the threshold gets streamed in 4 MiB chunks.
        if Int64(data.count) > singleShotMax {
            return resumable.upload(roomId: roomId, filename: filename, data: data)
        }
        return singleShot(roomId: roomId, filename: filename, data: data)
    }

    public func download(roomId: Int64, fileId: String) -> AsyncStream<TransferProgress> {
        AsyncStream { cont in
            Task {
                let keyHex: String
                switch await keys.keyFor(roomId) {
                case .ready(let hex, _): keyHex = hex
                case .pending(let r):    cont.yield(.error("no_room_key:\(r)")); cont.finish(); return
                case .error(let r):      cont.yield(.error(r));                  cont.finish(); return
                }
                do {
                    let raw = try await http.send(.get("api/files/\(fileId)"))
                    let ctHex = (String(data: raw, encoding: .utf8) ?? "")
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    let packed = try Hex.decode(ctHex)
                    let key = try Hex.decode(keyHex)
                    let plain = try self.aead.decrypt(key: key, packed: packed)
                    cont.yield(.done(fileId: fileId,
                                     ciphertextHashHex: Hex.encode(try sha256(packed)),
                                     plaintext: plain))
                } catch {
                    cont.yield(.error((error as NSError).localizedDescription))
                }
                cont.finish()
            }
        }
    }

    // MARK: single-shot ------------------------------------------------

    private func singleShot(roomId: Int64, filename: String, data: Data) -> AsyncStream<TransferProgress> {
        AsyncStream { cont in
            Task {
                let keyHex: String
                switch await keys.keyFor(roomId) {
                case .ready(let hex, _): keyHex = hex
                case .pending(let r):    cont.yield(.error("no_room_key:\(r)")); cont.finish(); return
                case .error(let r):      cont.yield(.error(r));                  cont.finish(); return
                }
                do {
                    let key = try Hex.decode(keyHex)
                    let packed = try self.aead.encrypt(key: key, plaintext: data)
                    let ctHex = Hex.encode(packed)
                    cont.yield(.inFlight(done: Int64(data.count), total: Int64(data.count)))

                    let req = try HttpRequest.postJson(
                        "api/files/upload",
                        body: UploadReq(room_id: roomId, filename: filename, ciphertext_hex: ctHex),
                    )
                    let resp = try await self.http.send(req, UploadResp.self)
                    cont.yield(.done(
                        fileId: resp.file_id,
                        ciphertextHashHex: Hex.encode(try sha256(packed)),
                        plaintext: nil,
                    ))
                } catch {
                    cont.yield(.error((error as NSError).localizedDescription))
                }
                cont.finish()
            }
        }
    }

    // MARK: DTOs -------------------------------------------------------

    private struct UploadReq: Encodable {
        let room_id: Int64
        let filename: String
        let ciphertext_hex: String
    }
    private struct UploadResp: Decodable {
        let file_id: String
        let size: Int64?
    }
}

/// CryptoKit hash helper kept private so we don't pull it into the
/// public API surface.
@inline(__always)
func sha256(_ bytes: Data) throws -> Data {
    // Small indirection — lets the caller stay blissfully ignorant of
    // CryptoKit types (and we avoid re-import cycles between
    // Files <-> VortexCrypto).
    var hasher = _Sha256()
    hasher.update(bytes)
    return hasher.final()
}

import CryptoKit
private struct _Sha256 {
    private var h = SHA256()
    mutating func update(_ d: Data) { h.update(data: d) }
    mutating func final() -> Data { Data(h.finalize()) }
}
