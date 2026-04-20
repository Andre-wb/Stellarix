import Foundation
import VortexCrypto
import Bootstrap
import Net
import Auth

/// Composition root. Wires each feature's factory to produce a single
/// object graph that screens pull their dependencies from.
public final class AppEnvironment {

    public static let shared = AppEnvironment()

    public let version: String = "0.1.0"
    public let crypto: VortexCryptoFactory
    public let bootstrap: BootstrapFactory
    public let auth: AuthFactory
    public let http: HttpClient
    public let cryptoPreview: CryptoPreview

    private init() {
        let crypto = VortexCryptoFactory()
        let bootstrap = BootstrapFactory()
        let baseProv  = BaseUrlProviderFromPrefs(prefs: bootstrap.prefs)
        let auth = AuthFactory(baseUrlProvider: baseProv)

        self.crypto = crypto
        self.bootstrap = bootstrap
        self.auth = auth
        self.http = auth.http
        self.cryptoPreview = CryptoPreview.makeFrom(crypto: crypto)
    }
}

public struct CryptoPreview {
    public let x25519Short: String
    public let ed25519Short: String

    static func makeFrom(crypto: VortexCryptoFactory) -> CryptoPreview {
        let x = crypto.keyAgreement.generateKeyPair()
        let e = crypto.signer.generateKeyPair()
        return .init(
            x25519Short: String(Hex.encode(x.publicKey).prefix(16)),
            ed25519Short: String(Hex.encode(e.publicKey).prefix(16)),
        )
    }
}
