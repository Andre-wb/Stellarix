import SwiftUI

/// Typed navigation path used by [RootScreen]. Each case carries just
/// enough to reconstruct the screen on deep-link / state restoration.
public enum Route: Hashable, Sendable {
    case chat(roomId: Int64)
    case call(roomId: Int64, video: Bool)
    case settings
    case spaces
    case bots
    case search
    case docs
    case ide
    case threads(roomId: Int64)
    case feeds(roomId: Int64)
}

@MainActor
public final class Router: ObservableObject {
    @Published public var path: [Route] = []
    public init() {}
    public func push(_ route: Route) { path.append(route) }
    public func pop()  { _ = path.popLast() }
    public func popToRoot() { path.removeAll() }
}
