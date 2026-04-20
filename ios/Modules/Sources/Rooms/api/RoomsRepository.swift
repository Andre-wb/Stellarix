import Foundation
import DB

/// Rooms list / create / join feature contract.
public protocol RoomsRepository: Sendable {
    func observe() -> AsyncStream<[RoomRecord]>
    func refresh() async -> RefreshResult
    func create(name: String, isPrivate: Bool) async -> RoomResult
    func joinByInvite(_ code: String) async -> RoomResult
    func leave(_ roomId: Int64) async -> Bool
}

public enum RefreshResult: Sendable, Equatable {
    case ok(count: Int)
    case error(String)
}

public enum RoomResult: Sendable, Equatable {
    case ok(roomId: Int64)
    case error(code: String, message: String)
}
