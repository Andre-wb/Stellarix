import Foundation

public protocol ThreadsRepository: Sendable {
    func observeForRoom(_ roomId: Int64) -> AsyncStream<[Thread]>
    func refresh(_ roomId: Int64) async -> Bool
    func create(roomId: Int64, parentMessageId: Int64, title: String) async -> Thread?
}

public struct Thread: Sendable, Equatable {
    public let id: Int64
    public let roomId: Int64
    public let parentMessageId: Int64
    public let title: String
    public let replyCount: Int
    public let lastReplyAt: Int64?
    public init(id: Int64, roomId: Int64, parentMessageId: Int64, title: String,
                replyCount: Int, lastReplyAt: Int64?) {
        self.id = id; self.roomId = roomId; self.parentMessageId = parentMessageId
        self.title = title; self.replyCount = replyCount; self.lastReplyAt = lastReplyAt
    }
}
