import Foundation

/// Long-lived WebSocket to the node. Single responsibility: keep a
/// connection open and hand out events. Frame encode/decode + room
/// key handling live in higher layers.
public protocol WsClient: Sendable {
    var state: AsyncStream<WsState> { get }
    var incoming: AsyncStream<String> { get }
    func start() async
    func stop() async
    func send(_ text: String) async
}

public enum WsState: Sendable, Equatable {
    case disconnected
    case connecting
    case connected
    case failed(reason: String)
}
