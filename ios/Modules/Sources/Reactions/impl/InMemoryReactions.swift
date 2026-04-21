import Foundation

public final class InMemoryReactions: Reactions, @unchecked Sendable {
    private var counts: [Int64: [String: Int]] = [:]
    private var mine: [Int64: Set<String>] = [:]
    private let lock = NSLock()

    public init() {}

    public func reactions(for messageId: Int64) -> [Reaction] {
        lock.lock(); defer { lock.unlock() }
        let mineSet = mine[messageId] ?? []
        return (counts[messageId] ?? [:])
            .map { Reaction(messageId: messageId, emoji: $0.key, count: $0.value, reactedByMe: mineSet.contains($0.key)) }
            .sorted { $0.count > $1.count }
    }

    public func apply(messageId: Int64, emoji: String, delta: Int, byMe: Bool) {
        lock.lock(); defer { lock.unlock() }
        var m = counts[messageId] ?? [:]
        m[emoji, default: 0] += delta
        if m[emoji, default: 0] <= 0 { m.removeValue(forKey: emoji) }
        counts[messageId] = m
        if byMe {
            var mset = mine[messageId] ?? []
            if delta > 0 { mset.insert(emoji) } else { mset.remove(emoji) }
            mine[messageId] = mset
        }
    }
}
