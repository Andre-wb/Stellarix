import Foundation

/// Auth feature contract. The UI layer depends on this protocol only —
/// the impl knows URLSession, JSON, and the endpoint shape.
public protocol AuthRepository: AnyObject, Sendable {
    var session: AsyncStream<Session> { get }
    func currentSession() -> Session

    func register(username: String, password: Data) async -> AuthResult
    func login(username: String, password: Data) async -> AuthResult
    func logout() async
}

public enum AuthResult: Sendable, Equatable {
    case ok
    case error(code: String, message: String)
}

public enum Session: Sendable, Equatable {
    case loggedOut
    case loggedIn(username: String)
}
