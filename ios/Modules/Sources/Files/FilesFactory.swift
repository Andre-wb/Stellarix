import Foundation
import Net
import VortexCrypto
import Keys

public struct FilesFactory {
    public let service: FileTransferService
    public let resumable: ResumableUpload

    public init(http: HttpClient, crypto: VortexCryptoFactory, keys: RoomKeyProvider) {
        let r = ResumableUpload(http: http, aead: crypto.aead, keys: keys)
        self.resumable = r
        self.service = HttpFileTransferService(
            http: http, aead: crypto.aead, keys: keys, resumable: r,
        )
    }
}
