import Foundation

/// E2E-encrypted file transfer. Streams chunks via `AsyncStream` so UI
/// can bind a progress bar without polling. Auto-switches to a chunked
/// resumable upload above a configurable threshold (Wave 14).
public protocol FileTransferService: Sendable {
    func upload(roomId: Int64, filename: String, data: Data) -> AsyncStream<TransferProgress>
    func download(roomId: Int64, fileId: String) -> AsyncStream<TransferProgress>
}

public enum TransferProgress: Sendable {
    case inFlight(done: Int64, total: Int64)
    case done(fileId: String, ciphertextHashHex: String, plaintext: Data?)
    case error(String)
}

public protocol MediaViewer: Sendable {
    func show(fileId: String, roomId: Int64, mimeType: String)
}
