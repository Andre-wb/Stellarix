import Foundation
import Bootstrap

/// Composition helper — assembles the URLSession stack.
///
/// `tokens` is a parameter because the default Wave 4 binding uses a
/// [NullAuthTokenSource] (no session yet); Wave 5's Auth module swaps
/// it for a Keychain-backed source without any caller change.
public struct NetFactory {
    public let base: BaseUrlProvider
    public let http: HttpClient

    public init(prefs: NodePreferences, tokens: AuthTokenSource = NullAuthTokenSource()) {
        let base = BaseUrlProviderFromPrefs(prefs: prefs)
        self.base = base
        self.http = URLSessionHttpClient(base: base, tokens: tokens)
    }
}

/// Placeholder used before Auth wires the Keychain source. Always
/// reports "not logged in".
public final class NullAuthTokenSource: AuthTokenSource {
    public init() {}
    public func accessToken() async -> String?  { nil }
    public func refreshToken() async -> String? { nil }
    public func refresh() async -> Bool         { false }
}
