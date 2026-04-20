import Foundation
import Net

/// Concrete [AuthRepository] + [AuthTokenSource]. One class serves both
/// roles: the token source reads from Keychain (what the HTTP layer
/// needs), while the repo writes on login/refresh (what the Auth UI
/// calls). Splitting them would duplicate the Keychain access path.
public final class AuthRepositoryImpl: AuthRepository, AuthTokenSource, @unchecked Sendable {

    private let http: HttpClient
    private let store: SecureStore
    private let sessionBridge = SessionBridge()

    private let keyAccess  = "jwt_access"
    private let keyRefresh = "jwt_refresh"
    private let keyUser    = "jwt_username"

    public init(http: HttpClient, store: SecureStore) {
        self.http = http
        self.store = store
    }

    // ── AuthRepository ─────────────────────────────────────────────────

    public var session: AsyncStream<Session> { sessionBridge.stream(initial: currentSession()) }

    public func currentSession() -> Session {
        if let u = store.getString(keyUser),
           store.getString(keyAccess) != nil {
            return .loggedIn(username: u)
        }
        return .loggedOut
    }

    public func register(username: String, password: Data) async -> AuthResult {
        await authCall(path: "api/authentication/register", username: username, password: password)
    }

    public func login(username: String, password: Data) async -> AuthResult {
        await authCall(path: "api/authentication/login", username: username, password: password)
    }

    public func logout() async {
        store.setString(keyAccess,  nil)
        store.setString(keyRefresh, nil)
        store.setString(keyUser,    nil)
        sessionBridge.publish(.loggedOut)
    }

    // ── AuthTokenSource ────────────────────────────────────────────────

    public func accessToken() async -> String?  { store.getString(keyAccess) }
    public func refreshToken() async -> String? { store.getString(keyRefresh) }

    /// Called by the HTTP layer on 401. Posts the stored refresh token
    /// to `/api/authentication/refresh` and stores the new access (and
    /// optionally refresh) token. Returns whether a fresh access is now
    /// in the Keychain.
    public func refresh() async -> Bool {
        guard let rt = store.getString(keyRefresh) else { return false }
        do {
            let req = try HttpRequest.postJson("api/authentication/refresh", body: RefreshReq(refresh_token: rt))
            let resp = try await http.send(req, AuthResp.self)
            store.setString(keyAccess, resp.access_token)
            if let nr = resp.refresh_token { store.setString(keyRefresh, nr) }
            return true
        } catch {
            return false
        }
    }

    // ── internals ──────────────────────────────────────────────────────

    private func authCall(path: String, username: String, password: Data) async -> AuthResult {
        do {
            let pw = String(data: password, encoding: .utf8) ?? ""
            let req = try HttpRequest.postJson(path, body: AuthReq(username: username, password: pw))
            let resp = try await http.send(req, AuthResp.self)
            store.setString(keyAccess,  resp.access_token)
            store.setString(keyRefresh, resp.refresh_token)
            store.setString(keyUser,    username)
            sessionBridge.publish(.loggedIn(username: username))
            return .ok
        } catch let HttpError.status(code, body) {
            return .error(code: "http_\(code)", message: body)
        } catch {
            return .error(code: "io", message: (error as NSError).localizedDescription)
        }
    }

    private struct AuthReq: Encodable { let username: String; let password: String }
    private struct RefreshReq: Encodable { let refresh_token: String }
    private struct AuthResp: Decodable {
        let access_token: String
        let refresh_token: String?
    }
}

/// Thread-safe fan-out of session updates to every observer.
private final class SessionBridge: @unchecked Sendable {
    private let lock = NSLock()
    private var continuations: [UUID: AsyncStream<Session>.Continuation] = [:]
    private var last: Session = .loggedOut

    func publish(_ s: Session) {
        lock.lock()
        last = s
        let copy = continuations.values
        lock.unlock()
        for c in copy { c.yield(s) }
    }

    func stream(initial: Session) -> AsyncStream<Session> {
        AsyncStream { cont in
            lock.lock(); let start = last; lock.unlock()
            cont.yield(start == .loggedOut ? initial : start)
            let id = UUID()
            lock.lock(); continuations[id] = cont; lock.unlock()
            cont.onTermination = { @Sendable _ in
                self.lock.lock(); self.continuations.removeValue(forKey: id); self.lock.unlock()
            }
        }
    }
}
