import Foundation
import GRDB

public struct BotRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var id: Int64
    public var name: String
    public var author: String
    public var shortDescription: String
    public var avatarUrl: String?
    public var installed: Bool
    public var rating: Double
    public var installCount: Int64

    public static let databaseTableName = "bots"

    public init(id: Int64, name: String, author: String = "",
                shortDescription: String = "", avatarUrl: String? = nil,
                installed: Bool = false, rating: Double = 0, installCount: Int64 = 0) {
        self.id = id; self.name = name; self.author = author
        self.shortDescription = shortDescription; self.avatarUrl = avatarUrl
        self.installed = installed; self.rating = rating; self.installCount = installCount
    }
}
