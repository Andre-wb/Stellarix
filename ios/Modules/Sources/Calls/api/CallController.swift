import Foundation

public protocol CallController: Sendable {
    var state: AsyncStream<CallState> { get }
    func start(roomId: Int64, video: Bool) async -> CallHandle
    func answer(_ invitation: CallInvitation) async
    func hangup() async
    func toggleMic(_ on: Bool) async
    func toggleCamera(_ on: Bool) async
}

public enum CallState: Sendable, Equatable {
    case idle, ringing, connecting
    case connected(participantCount: Int)
    case ended(reason: String)
}

public struct CallHandle: Sendable, Equatable { public let callId: String
    public init(callId: String) { self.callId = callId } }
public struct CallInvitation: Sendable, Equatable {
    public let callId: String
    public let fromUserId: Int64
    public let video: Bool
    public init(callId: String, fromUserId: Int64, video: Bool) {
        self.callId = callId; self.fromUserId = fromUserId; self.video = video
    }
}

public protocol IceConfigProvider: Sendable {
    func current() async -> [IceServer]
}

public struct IceServer: Sendable, Equatable {
    public let urls: [String]
    public let username: String?
    public let credential: String?
    public init(urls: [String], username: String? = nil, credential: String? = nil) {
        self.urls = urls; self.username = username; self.credential = credential
    }
}
