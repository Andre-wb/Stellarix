import Foundation

public struct Reaction: Sendable, Codable, Hashable {
    public let messageId: Int64
    public let emoji: String
    public let count: Int
    public let reactedByMe: Bool
    public init(messageId: Int64, emoji: String, count: Int, reactedByMe: Bool) {
        self.messageId = messageId; self.emoji = emoji; self.count = count; self.reactedByMe = reactedByMe
    }
}

/// Client-side rollup over the `messageId → [emoji→count]` table. The
/// actual toggling still goes through [MessageActions.react]; this
/// aggregator just gives the UI a fast `Reactions.for(messageId)`.
public protocol Reactions: Sendable {
    func reactions(for messageId: Int64) -> [Reaction]
    func apply(messageId: Int64, emoji: String, delta: Int, byMe: Bool)
}
