import Foundation
import Net
import VortexCrypto

/// Assembles the Auth feature.
///
/// The repo needs a `KeyAgreement` so register calls can mint the
/// user's long-term X25519 keypair and hand its public half to the
/// node in the register payload — the node rejects registrations
/// without it (see `app/authentication/password.py`).
public struct AuthFactory {
    public let store: SecureStore
    public let repo: AuthRepository
    public let tokens: AuthTokenSource
    public let http: HttpClient

    public init(
        baseUrlProvider: BaseUrlProvider,
        crypto: VortexCryptoFactory = VortexCryptoFactory(),
        store: SecureStore = KeychainSecureStore(),
    ) {
        self.store = store
        let bootstrapHttp = URLSessionHttpClient(
            base: baseUrlProvider,
            tokens: NullAuthTokenSource(),
        )
        let repo = AuthRepositoryImpl(
            http: bootstrapHttp,
            store: store,
            keyAgreement: crypto.keyAgreement,
        )
        self.repo = repo
        self.tokens = repo
        self.http = URLSessionHttpClient(base: baseUrlProvider, tokens: repo)
    }
}
