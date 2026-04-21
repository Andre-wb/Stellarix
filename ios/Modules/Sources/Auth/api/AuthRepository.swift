import Foundation

/// Auth feature contract. The UI layer depends on this protocol only —
/// the impl knows URLSession, JSON, and the endpoint shape.
public protocol AuthRepository: AnyObject, Sendable {
    var session: AsyncStream<Session> { get }
    func currentSession() -> Session

    func register(username: String, password: Data) async -> AuthResult
    func registerFull(profile: RegisterProfile) async -> AuthResult
    func login(username: String, password: Data) async -> AuthResult
    func logout() async
}

/// Full registration payload matching the web form
/// (username + phone + display name + email + avatar emoji).
/// The node treats any missing optional field as "not set".
public struct RegisterProfile: Sendable {
    public let username: String
    public let password: Data
    public let phone: String?
    public let displayName: String?
    public let email: String?
    public let avatarEmoji: String?
    /// Raw JPEG/PNG bytes of a photo picked from the gallery. Uploaded
    /// after register/login succeeds — `/api/authentication/avatar`
    /// needs an access token, so it's a second roundtrip.
    public let avatarPhoto: Data?

    public init(username: String, password: Data,
                phone: String? = nil, displayName: String? = nil,
                email: String? = nil, avatarEmoji: String? = nil,
                avatarPhoto: Data? = nil) {
        self.username = username
        self.password = password
        self.phone = phone
        self.displayName = displayName
        self.email = email
        self.avatarEmoji = avatarEmoji
        self.avatarPhoto = avatarPhoto
    }
}

public enum AuthResult: Sendable, Equatable {
    case ok
    case error(code: String, message: String)
}

public enum Session: Sendable, Equatable {
    case loggedOut
    case loggedIn(username: String)
}
