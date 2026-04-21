import Foundation

public struct ReactionsFactory {
    public let reactions: Reactions
    public init() { self.reactions = InMemoryReactions() }
}
