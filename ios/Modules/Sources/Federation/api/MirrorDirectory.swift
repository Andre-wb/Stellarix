import Foundation

public protocol MirrorDirectory: Sendable {
    var mirrors: AsyncStream<[Mirror]> { get }
    func refresh() async -> Bool
    func probe(_ mirrorId: String) async -> Bool
}

public struct Mirror: Sendable, Equatable {
    public let id: String
    public let url: String
    public let kind: String              // "tunnel" | "tor" | "ipfs" | "direct"
    public let lastSeenEpoch: Int64?
    public let healthy: Bool
    public init(id: String, url: String, kind: String, lastSeenEpoch: Int64?, healthy: Bool) {
        self.id = id; self.url = url; self.kind = kind
        self.lastSeenEpoch = lastSeenEpoch; self.healthy = healthy
    }
}
