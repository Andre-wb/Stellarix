import Foundation

public protocol BotsRepository: Sendable {
    var marketplace: AsyncStream<[Bot]> { get }
    var installed: AsyncStream<[Bot]> { get }
    func refreshMarketplace() async -> Bool
    func install(_ id: Int64) async -> Bool
    func uninstall(_ id: Int64) async -> Bool
}

public struct Bot: Sendable, Equatable {
    public let id: Int64
    public let name: String
    public let author: String
    public let shortDescription: String
    public let avatarUrl: String?
    public let installed: Bool
    public let rating: Double
    public let installCount: Int64
    public init(id: Int64, name: String, author: String, shortDescription: String,
                avatarUrl: String?, installed: Bool, rating: Double, installCount: Int64) {
        self.id = id; self.name = name; self.author = author
        self.shortDescription = shortDescription; self.avatarUrl = avatarUrl
        self.installed = installed; self.rating = rating; self.installCount = installCount
    }
}
