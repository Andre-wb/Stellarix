import Foundation
import Net
import DB
import VortexCrypto
import Identity

public struct RoomsFactory {
    public let repo: RoomsRepository

    public init(
        http: HttpClient,
        db: DBFactory,
        crypto: VortexCryptoFactory,
        identity: IdentityRepository,
    ) {
        self.repo = HttpRoomsRepository(
            http: http,
            rooms: db.rooms,
            roomKeys: db.roomKeys,
            aead: crypto.aead,
            keyAgreement: crypto.keyAgreement,
            kdf: crypto.kdf,
            random: crypto.random,
            identity: identity,
        )
    }
}
