import Foundation
import Net

/// Assembles the Auth feature.
///
/// Consumes Net's `httpBuilder` so the `HttpClient` is created AFTER the
/// Keychain-backed token source exists — guaranteeing HTTP calls from
/// any feature carry a Bearer header from the very first request.
public struct AuthFactory {
    public let store: SecureStore
    public let repo: AuthRepository
    public let tokens: AuthTokenSource
    public let http: HttpClient

    public init(
        baseUrlProvider: BaseUrlProvider,
        store: SecureStore = KeychainSecureStore(),
    ) {
        self.store = store
        // Build a two-phase graph: a lightweight HttpClient without auth
        // first (so refresh() can call /authentication/refresh), then
        // wrap it in the real repo. The real HttpClient that every
        // feature downstream consumes uses this repo as its AuthTokenSource.
        let bootstrapHttp = URLSessionHttpClient(
            base: baseUrlProvider,
            tokens: NullAuthTokenSource(),
        )
        let repo = AuthRepositoryImpl(http: bootstrapHttp, store: store)
        self.repo = repo
        self.tokens = repo
        self.http = URLSessionHttpClient(base: baseUrlProvider, tokens: repo)
    }
}
