import Foundation

public protocol SpacesRepository: Sendable {
    var spaces: AsyncStream<[Space]> { get }
    func refresh() async -> Bool
    func create(name: String, isPublic: Bool) async -> Space?
    func leave(_ id: Int64) async -> Bool
}

public struct Space: Sendable, Equatable {
    public let id: Int64
    public let name: String
    public let ownerId: Int64
    public let avatarEmoji: String
    public let memberCount: Int
    public let isPublic: Bool
    public init(id: Int64, name: String, ownerId: Int64, avatarEmoji: String, memberCount: Int, isPublic: Bool) {
        self.id = id; self.name = name; self.ownerId = ownerId
        self.avatarEmoji = avatarEmoji; self.memberCount = memberCount; self.isPublic = isPublic
    }
}
