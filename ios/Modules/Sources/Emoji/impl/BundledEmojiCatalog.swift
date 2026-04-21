import Foundation

/// Loads `emoji.json` from the module bundle once, exposes it via
/// [EmojiCatalog], and persists recents to UserDefaults under
/// "vortex.emoji.recent" (a JSON array of strings).
public final class BundledEmojiCatalog: EmojiCatalog, @unchecked Sendable {
    private let data: [EmojiCategory: [String]]
    private let index: [String]   // flat list for search
    private let defaults: UserDefaults
    private let recentsKey = "vortex.emoji.recent"
    private let recentsCap = 30
    private let lock = NSLock()

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        var parsed: [EmojiCategory: [String]] = [:]
        if let url = Bundle.module.url(forResource: "emoji", withExtension: "json"),
           let raw = try? Data(contentsOf: url),
           let obj = try? JSONSerialization.jsonObject(with: raw) as? [String: [String]] {
            for (k, v) in obj {
                if let cat = EmojiCategory(rawValue: k) { parsed[cat] = v }
            }
        }
        self.data = parsed
        self.index = EmojiCategory.allCases
            .filter { $0 != .recent }
            .compactMap { parsed[$0] }
            .flatMap { $0 }
    }

    public func categories() -> [EmojiCategory] { EmojiCategory.allCases }

    public func emojis(in category: EmojiCategory) -> [String] {
        if category == .recent { return recent() }
        return data[category] ?? []
    }

    public func search(_ query: String) -> [String] {
        // Substring search over the raw character is limited; most useful
        // cases are exact character paste or empty → all. A proper
        // annotation-based search would need a names dataset.
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return index }
        return index.filter { $0.contains(q) }
    }

    public func recent() -> [String] {
        lock.lock(); defer { lock.unlock() }
        return (defaults.array(forKey: recentsKey) as? [String]) ?? []
    }

    public func bumpRecent(_ emoji: String) {
        lock.lock(); defer { lock.unlock() }
        var list = (defaults.array(forKey: recentsKey) as? [String]) ?? []
        list.removeAll { $0 == emoji }
        list.insert(emoji, at: 0)
        if list.count > recentsCap { list = Array(list.prefix(recentsCap)) }
        defaults.set(list, forKey: recentsKey)
    }
}
