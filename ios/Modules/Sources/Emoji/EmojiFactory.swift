import Foundation

public struct EmojiFactory {
    public let catalog: EmojiCatalog
    public init() { self.catalog = BundledEmojiCatalog() }
}
