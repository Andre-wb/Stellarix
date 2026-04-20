import Foundation
import Bootstrap

/// Reads the user-chosen base URL from the Bootstrap feature's prefs.
public final class BaseUrlProviderFromPrefs: BaseUrlProvider {
    private let prefs: NodePreferences
    public init(prefs: NodePreferences) { self.prefs = prefs }
    public func current() -> String? { prefs.currentBaseUrl() }
}
