import Foundation
import Net
import VortexCrypto

/// Concrete [AuthRepository] + [AuthTokenSource]. One class serves both
/// roles: the token source reads from Keychain (what the HTTP layer
/// needs), while the repo writes on login/refresh (what the Auth UI
/// calls). Splitting them would duplicate the Keychain access path.
public final class AuthRepositoryImpl: AuthRepository, AuthTokenSource, @unchecked Sendable {

    private let http: HttpClient
    private let store: SecureStore
    private let keyAgreement: KeyAgreement
    private let sessionBridge = SessionBridge()

    private let keyAccess  = "jwt_access"
    private let keyRefresh = "jwt_refresh"
    private let keyUser    = "jwt_username"
    private let keyX25519Priv = "x25519_private"
    private let keyX25519Pub  = "x25519_public"

    public init(http: HttpClient, store: SecureStore, keyAgreement: KeyAgreement) {
        self.http = http
        self.store = store
        self.keyAgreement = keyAgreement
    }

    /// Reuse the device's long-term X25519 keypair if one is already
    /// stored, otherwise mint a fresh one. Returns the public key as a
    /// 64-char hex string — the format the node expects.
    private func ensureX25519Pubkey() -> (privHex: String, pubHex: String) {
        if let p = store.getString(keyX25519Priv),
           let u = store.getString(keyX25519Pub),
           p.count == 64, u.count == 64 {
            return (p, u)
        }
        let kp = keyAgreement.generateKeyPair()
        let priv = Hex.encode(kp.privateKey)
        let pub  = Hex.encode(kp.publicKey)
        store.setString(keyX25519Priv, priv)
        store.setString(keyX25519Pub, pub)
        return (priv, pub)
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
        await registerFull(profile: RegisterProfile(username: username, password: password))
    }

    public func registerFull(profile: RegisterProfile) async -> AuthResult {
        do {
            let pw = String(data: profile.password, encoding: .utf8) ?? ""
            let keys = ensureX25519Pubkey()
            let body = FullAuthReq(
                username: profile.username,
                password: pw,
                phone: profile.phone,
                display_name: profile.displayName ?? "",
                email: profile.email,
                avatar_emoji: profile.avatarEmoji ?? "👤",
                x25519_public_key: keys.pubHex,
            )
            let req = try HttpRequest.postJson("api/authentication/register", body: body)
            let resp = try await http.send(req, AuthResp.self)
            store.setString(keyAccess, resp.access_token)
            store.setString(keyRefresh, resp.refresh_token)
            store.setString(keyUser, profile.username)
            sessionBridge.publish(.loggedIn(username: profile.username))
            // Upload gallery photo (if any) as a separate multipart
            // call — /api/authentication/avatar needs a JWT, and the
            // register endpoint itself doesn't accept file bodies.
            // We deliberately don't fail the whole register() if the
            // photo upload errors out; the account is already created.
            if let photo = profile.avatarPhoto, !photo.isEmpty {
                await uploadAvatar(photo: photo)
            }
            return .ok
        } catch {
            return Self.mapHttpError(error)
        }
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
        } catch {
            return Self.mapHttpError(error)
        }
    }

    /// Central error → AuthResult mapper. Keeps registerFull() and
    /// authCall() in lockstep and — critically — unpacks `HttpError`
    /// cases properly. An earlier `catch let HttpError.status(c, b)`
    /// pattern looked right but fell through at runtime, leaking raw
    /// "Net.HttpError error 2" NSError descriptions to the UI.
    static func mapHttpError(_ error: Error) -> AuthResult {
        if let h = error as? HttpError {
            switch h {
            case .noBaseUrl:
                return .error(code: "no_base_url",
                              message: "No server configured. Go back and enter a URL.")
            case .malformedUrl(let url):
                return .error(code: "bad_url", message: "Bad URL: \(url)")
            case .status(let code, let body):
                // Server usually replies with JSON {"error":"…"}; extract
                // that if we can so the user sees "Password too weak"
                // instead of the raw JSON envelope.
                let nice = extractErrorText(body) ?? body
                return .error(code: "http_\(code)", message: nice)
            case .notJson:
                return .error(code: "not_json",
                              message: "Server returned unexpected data.")
            case .transport(let msg):
                return .error(code: "transport", message: msg)
            }
        }
        return .error(code: "io", message: (error as NSError).localizedDescription)
    }

    private func uploadAvatar(photo: Data) async {
        // Build an RFC 7578 multipart body manually — `Net.HttpRequest`
        // doesn't ship a multipart builder and pulling one in for a
        // single endpoint isn't worth the dependency.
        let boundary = "----VortexAvatar\(UUID().uuidString)"
        var body = Data()
        let prelude = "--\(boundary)\r\n"
            + "Content-Disposition: form-data; name=\"file\"; filename=\"avatar.jpg\"\r\n"
            + "Content-Type: image/jpeg\r\n\r\n"
        body.append(prelude.data(using: .utf8)!)
        body.append(photo)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        let req = HttpRequest(
            method: .POST,
            path: "api/authentication/avatar",
            body: body,
            extraHeaders: [
                "Content-Type": "multipart/form-data; boundary=\(boundary)",
            ],
        )
        _ = try? await http.send(req)
    }

    private static func extractErrorText(_ body: String) -> String? {
        guard let data = body.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let e = obj["error"] as? String { return e }
        if let d = obj["detail"] as? String { return d }
        if let items = obj["details"] as? [[String: Any]] {
            let msgs = items.compactMap { $0["message"] as? String }
            if !msgs.isEmpty { return msgs.joined(separator: "\n") }
        }
        return nil
    }

    private struct AuthReq: Encodable { let username: String; let password: String }
    private struct FullAuthReq: Encodable {
        let username: String
        let password: String
        let phone: String?
        let display_name: String
        let email: String?
        let avatar_emoji: String
        let x25519_public_key: String
    }
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
