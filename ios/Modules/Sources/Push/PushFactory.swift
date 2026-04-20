import Foundation
import Net
import VortexCrypto

public struct PushFactory {
    public let subscriber: APNsPushSubscriber
    public init(http: HttpClient, crypto: VortexCryptoFactory) {
        self.subscriber = APNsPushSubscriber(
            http: http,
            keyAgreement: crypto.keyAgreement,
            random: crypto.random,
        )
    }
}
