import Foundation

/// Category of emoji pulled from the bundled `emoji.json`. The order is
/// the same as the tab order in the picker.
public enum EmojiCategory: String, CaseIterable, Sendable, Hashable {
    case recent, smileys, people, animals, food, travel, activities, objects, symbols, flags

    /// Tab icon used to switch categories. "recent" uses a clock.
    public var tabIcon: String {
        switch self {
        case .recent:     return "🕑"
        case .smileys:    return "😀"
        case .people:     return "👋"
        case .animals:    return "🐶"
        case .food:       return "🍎"
        case .travel:     return "🚗"
        case .activities: return "⚽"
        case .objects:    return "💡"
        case .symbols:    return "❤️"
        case .flags:      return "🏁"
        }
    }
}

/// Read-only access to the bundled emoji catalog, plus a small ring of
/// "recently used" entries persisted to UserDefaults.
public protocol EmojiCatalog: Sendable {
    /// Categories in display order, minus `.recent` which is returned by
    /// [recent()].
    func categories() -> [EmojiCategory]

    /// All emojis in the given category, in catalog order.
    func emojis(in category: EmojiCategory) -> [String]

    /// Fuzzy match by case-insensitive substring of the character (used
    /// for ":smile" style queries). Empty query returns every emoji.
    func search(_ query: String) -> [String]

    /// Most-recently-used, newest first, capped at ~30.
    func recent() -> [String]

    /// Bump [emoji] to the front of the MRU ring.
    func bumpRecent(_ emoji: String)
}
