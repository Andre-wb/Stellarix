import Foundation
import Net
import Auth
import VortexCrypto

/// Accounts list persisted in UserDefaults; per-account JWT and static
/// X25519 seed live in the Keychain under derived keys
/// `account.<id>.jwt` and `account.<id>.x25519`.
///
/// [switchTo] executes a two-step dance with the target node:
///   1. POST /api/auth/challenge  → { nonce_b64 }
///   2. sign(nonce, x25519-derived-ed25519) then
///      POST /api/auth/challenge/verify → { jwt }
/// The resulting JWT replaces the active token via [AuthRepository].
public actor KeychainAccountsManager: AccountsManager {
    private let defaults: UserDefaults
    private let store: SecureStore
    private let http: (String) -> HttpClient   // per-baseUrl factory
    private let onActiveChanged: (SavedAccount, String) -> Void
    private let listKey = "vortex.accounts"
    private let activeKey = "vortex.accounts.active"

    public init(defaults: UserDefaults = .standard,
                store: SecureStore,
                http: @escaping (String) -> HttpClient,
                onActiveChanged: @escaping (SavedAccount, String) -> Void) {
        self.defaults = defaults
        self.store = store
        self.http = http
        self.onActiveChanged = onActiveChanged
    }

    public func list() -> [SavedAccount] {
        guard let raw = defaults.data(forKey: listKey),
              let list = try? JSONDecoder().decode([SavedAccount].self, from: raw) else { return [] }
        return list
    }

    public func active() -> SavedAccount? {
        guard let id = defaults.string(forKey: activeKey) else { return nil }
        return list().first { $0.id == id }
    }

    public func add(_ account: SavedAccount, jwt: String, staticKeySeedB64: String) async {
        var list = self.list()
        list.removeAll { $0.id == account.id }
        list.append(account)
        if let raw = try? JSONEncoder().encode(list) { defaults.set(raw, forKey: listKey) }
        store.setString("account.\(account.id).jwt", jwt)
        store.setString("account.\(account.id).x25519", staticKeySeedB64)
        if active() == nil { defaults.set(account.id, forKey: activeKey) }
    }

    public func remove(id: String) async {
        var list = self.list()
        list.removeAll { $0.id == id }
        if let raw = try? JSONEncoder().encode(list) { defaults.set(raw, forKey: listKey) }
        store.setString("account.\(id).jwt", nil)
        store.setString("account.\(id).x25519", nil)
        if defaults.string(forKey: activeKey) == id {
            defaults.set(list.first?.id, forKey: activeKey)
        }
    }

    public func switchTo(id: String) async throws -> SavedAccount {
        guard let acct = list().first(where: { $0.id == id }) else {
            throw AccountsError.unknownAccount
        }
        guard let seedB64 = store.getString("account.\(id).x25519"),
              let seed = Data(base64Encoded: seedB64) else {
            throw AccountsError.challengeFailed
        }
        let client = http(acct.baseUrl)
        let nonce = try await fetchChallenge(client: client, username: acct.username)
        let signed = try signNonce(nonce: nonce, seed: seed)
        let jwt = try await verifyChallenge(client: client,
                                            username: acct.username,
                                            nonce: nonce,
                                            signature: signed)
        store.setString("account.\(id).jwt", jwt)
        defaults.set(id, forKey: activeKey)
        onActiveChanged(acct, jwt)
        return acct
    }

    // MARK: - Challenge helpers

    private struct ChallengeResp: Codable { let nonce_b64: String }
    private struct VerifyReq: Codable { let username: String; let nonce_b64: String; let signature_b64: String }
    private struct VerifyResp: Codable { let jwt: String }

    private func fetchChallenge(client: HttpClient, username: String) async throws -> Data {
        let body = ["username": username]
        let req = try HttpRequest.postJson("/api/auth/challenge", body: body)
        let resp: ChallengeResp
        do { resp = try await client.send(req, ChallengeResp.self) }
        catch { throw AccountsError.refreshFailed("\(error)") }
        guard let d = Data(base64Encoded: resp.nonce_b64) else { throw AccountsError.challengeFailed }
        return d
    }

    private func signNonce(nonce: Data, seed: Data) throws -> String {
        // The server expects an Ed25519 signature over the raw nonce,
        // keyed with the user's signing key (seed == raw private key).
        let signer = Ed25519Signer()
        let sig = try signer.sign(privateKey: seed, message: nonce)
        return sig.base64EncodedString()
    }

    private func verifyChallenge(client: HttpClient, username: String, nonce: Data, signature: String) async throws -> String {
        let body = VerifyReq(username: username,
                             nonce_b64: nonce.base64EncodedString(),
                             signature_b64: signature)
        let req = try HttpRequest.postJson("/api/auth/challenge/verify", body: body)
        do {
            let r = try await client.send(req, VerifyResp.self)
            return r.jwt
        } catch {
            throw AccountsError.refreshFailed("\(error)")
        }
    }
}
