import Foundation
import Combine

/// Synchronous translator for SwiftUI views.
///
/// The existing [LocaleSource] has an async `translate()` API which is
/// fine for one-off fetches but painful from a `View.body` — SwiftUI
/// can't suspend on each label. This class loads the current locale's
/// JSON bundle once, flattens it into a dot-keyed dictionary, and
/// publishes updates so any view observing it re-renders when the user
/// switches languages.
@MainActor
public final class Localizer: ObservableObject {
    @Published public private(set) var locale: String
    @Published public private(set) var strings: [String: String] = [:]

    private let bundle: Bundle
    private let defaults: UserDefaults

    public init(bundle: Bundle? = nil, defaults: UserDefaults = .standard) {
        self.bundle = bundle ?? .module
        self.defaults = defaults
        let saved = defaults.string(forKey: "locale") ?? "en"
        self.locale = saved
        self.strings = Self.load(locale: saved, bundle: self.bundle)
    }

    public func setLocale(_ code: String) {
        guard code != locale else { return }
        locale = code
        strings = Self.load(locale: code, bundle: bundle)
        defaults.set(code, forKey: "locale")
    }

    /// Dot-path lookup: `t("auth.login") → "Войти"`. If the current
    /// locale doesn't have that key, fall back to the English bundle;
    /// if that also misses, return the key itself so missing strings
    /// stay visible in QA instead of silently blanking the UI.
    public func t(_ key: String, default fallback: String? = nil) -> String {
        if let v = strings[key] { return v }
        if locale != "en",
           let v = Self.load(locale: "en", bundle: bundle)[key] {
            return v
        }
        return fallback ?? key
    }

    public subscript(key: String) -> String { t(key) }

    // MARK: - Loader

    private static func load(locale: String, bundle: Bundle) -> [String: String] {
        guard let url = bundle.url(forResource: locale, withExtension: "json",
                                   subdirectory: "locales"),
              let raw = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: raw) as? [String: Any] else {
            return [:]
        }
        var out: [String: String] = [:]
        flatten(obj, prefix: "", into: &out)
        return out
    }

    private static func flatten(_ node: Any, prefix: String, into out: inout [String: String]) {
        if let dict = node as? [String: Any] {
            for (k, v) in dict {
                let p = prefix.isEmpty ? k : prefix + "." + k
                flatten(v, prefix: p, into: &out)
            }
        } else if let s = node as? String {
            out[prefix] = s
        } else if let n = node as? NSNumber {
            out[prefix] = n.stringValue
        }
    }
}
