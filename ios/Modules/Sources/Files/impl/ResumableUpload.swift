import Foundation
import CryptoKit
import Net
import VortexCrypto
import Keys

/// Chunked resumable upload for large files (> 10 MiB).
///
/// Each chunk is independently AES-GCM encrypted — partial uploads can
/// never leak the rest of the file if the server aborts mid-stream.
/// Protocol matches `scripts/integrity_repo.py` clients in the web flow:
///
///   POST  /api/files/resumable/start            → {upload_id}
///   PUT   /api/files/resumable/{id}/chunk?index → body = ciphertext hex
///   POST  /api/files/resumable/{id}/finish      → {file_id}
public final class ResumableUpload {
    private let http: HttpClient
    private let aead: Aead
    private let keys: RoomKeyProvider
    private let chunkSize: Int

    public init(http: HttpClient, aead: Aead, keys: RoomKeyProvider, chunkSize: Int = 4 * 1024 * 1024) {
        self.http = http
        self.aead = aead
        self.keys = keys
        self.chunkSize = chunkSize
    }

    public func upload(roomId: Int64, filename: String, data: Data) -> AsyncStream<TransferProgress> {
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

                    // 1. Begin session.
                    let start = try await http.send(
                        try HttpRequest.postJson(
                            "api/files/resumable/start",
                            body: StartReq(
                                room_id: roomId, filename: filename,
                                size_bytes: Int64(data.count),
                            ),
                        ),
                        StartResp.self,
                    )

                    // 2. Push chunks.
                    var hasher = SHA256()
                    var index = 0
                    var offset = 0
                    while offset < data.count {
                        let end = min(offset + chunkSize, data.count)
                        let chunk = data.subdata(in: offset..<end)
                        let ct = try aead.encrypt(key: key, plaintext: chunk)
                        hasher.update(data: ct)

                        let hex = Hex.encode(ct)
                        var req = HttpRequest(
                            method: .PUT,
                            path: "api/files/resumable/\(start.upload_id)/chunk",
                            body: hex.data(using: .utf8),
                            extraHeaders: ["Content-Type": "application/octet-stream"],
                            queryItems: [URLQueryItem(name: "index", value: String(index))],
                        )
                        _ = try await http.send(req)

                        offset = end
                        index += 1
                        cont.yield(.inFlight(done: Int64(offset), total: Int64(data.count)))
                    }

                    // 3. Finish session.
                    let finish = try await http.send(
                        HttpRequest(method: .POST,
                                    path: "api/files/resumable/\(start.upload_id)/finish"),
                        FinishResp.self,
                    )
                    cont.yield(.done(
                        fileId: finish.file_id,
                        ciphertextHashHex: Hex.encode(Data(hasher.finalize())),
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

    private struct StartReq: Encodable {
        let room_id: Int64
        let filename: String
        let size_bytes: Int64
    }
    private struct StartResp: Decodable  { let upload_id: String }
    private struct FinishResp: Decodable { let file_id: String }
}
