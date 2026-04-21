import Foundation

/// 146-language loader. Locale JSON files live in `Resources/locales/`
/// (same shape as web client's `/static/locales/*.json` and Android's
/// `assets/locales/`).
///
/// Lookup per `translate(key)`:
///   1. `ns.key` split — traverse nested JSON.
///   2. Fall back to the `en` bundle if missing.
///   3. Return the key itself so missing strings are visually obvious.
public final class AssetLocaleSource: LocaleSource, @unchecked Sendable {
    private let bundle: Bundle
    private let defaults: UserDefaults
    private let lock = NSLock()
    private var cache: [String: [String: Any]] = [:]
    private let currentBridge = Bridge()

    public init(bundle: Bundle? = nil, defaults: UserDefaults = .standard) {
        self.bundle = bundle ?? .module
        self.defaults = defaults
        currentBridge.publish(defaults.string(forKey: "locale") ?? pickDeviceDefault())
    }

    public var current: AsyncStream<String> { currentBridge.stream() }

    public func setLocale(_ code: String) async {
        defaults.set(code, forKey: "locale")
        currentBridge.publish(code)
    }

    public func translate(_ key: String) async -> String {
        let code = currentBridge.lastValue()
        if let value = lookup(key, in: code) { return value }
        if code != "en", let fallback = lookup(key, in: "en") { return fallback }
        return key
    }

    // MARK: internals --------------------------------------------------

    private func lookup(_ key: String, in code: String) -> String? {
        let bundle = loadBundle(code)
        var cursor: Any = bundle
        for part in key.split(separator: ".") {
            guard let dict = cursor as? [String: Any],
                  let next = dict[String(part)] else { return nil }
            cursor = next
        }
        return cursor as? String
    }

    private func loadBundle(_ code: String) -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        if let existing = cache[code] { return existing }
        guard let url = bundle.url(forResource: code, withExtension: "json", subdirectory: "locales"),
              let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { cache[code] = [:]; return [:] }
        cache[code] = obj
        return obj
    }

    private func pickDeviceDefault() -> String {
        let lang = (Locale.current.language.languageCode?.identifier ?? "en").lowercased()
        let region = (Locale.current.region?.identifier ?? "").uppercased()
        if lang == "zh" && region == "TW" { return "zh-TW" }
        return lang.isEmpty ? "en" : lang
    }

    private final class Bridge: @unchecked Sendable {
        private let lock = NSLock()
        private var subs: [UUID: AsyncStream<String>.Continuation] = [:]
        private var last: String = "en"
        func lastValue() -> String { lock.lock(); defer { lock.unlock() }; return last }
        func publish(_ v: String) {
            lock.lock(); last = v; let copy = subs.values; lock.unlock()
            for c in copy { c.yield(v) }
        }
        func stream() -> AsyncStream<String> {
            AsyncStream { cont in
                lock.lock(); cont.yield(last); let id = UUID(); subs[id] = cont; lock.unlock()
                cont.onTermination = { @Sendable _ in
                    self.lock.lock(); self.subs.removeValue(forKey: id); self.lock.unlock()
                }
            }
        }
    }
}
