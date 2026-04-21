import Foundation
#if canImport(UIKit)
import UIKit
#endif
import UserNotifications
import Net
import VortexCrypto

/// APNs-backed [PushSubscriber].
///
/// Flow:
///   1. Request `.alert | .sound | .badge` permission via UNUserNotificationCenter.
///   2. `UIApplication.shared.registerForRemoteNotifications()` —
///      the AppDelegate relays the device token to `deviceToken(_:)`.
///   3. Generate a fresh X25519 keypair + 16-byte auth secret and POST
///      `{endpoint: "apns://<hex>", p256dh, auth}` to `/api/push/subscribe`.
///      Node wraps each payload using the public key so even Apple's
///      servers can't read plaintext.
public final class APNsPushSubscriber: PushSubscriber, @unchecked Sendable {
    private let http: HttpClient
    private let keyAgreement: KeyAgreement
    private let random: SecureRandomProvider
    private let tokenLock = NSLock()
    private var cachedToken: String?

    public init(http: HttpClient, keyAgreement: KeyAgreement, random: SecureRandomProvider) {
        self.http = http
        self.keyAgreement = keyAgreement
        self.random = random
    }

    public func enable() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
            guard granted else { return false }
            // Ask for a token on main actor — UIKit requirement.
            #if canImport(UIKit)
            await MainActor.run {
                UIApplication.shared.registerForRemoteNotifications()
            }
            #endif
            // Wait up to 5s for the AppDelegate hook to call `deviceToken()`.
            let token = await waitForToken(timeout: 5)
            guard let token else { return false }

            let kp   = keyAgreement.generateKeyPair()
            let auth = random.nextBytes(16)
            let req  = try HttpRequest.postJson("api/push/subscribe",
                body: SubReq(endpoint: "apns://\(token)",
                             p256dh: Hex.encode(kp.publicKey),
                             auth: Hex.encode(auth)))
            _ = try await http.send(req)
            return true
        } catch { return false }
    }

    public func disable() async -> Bool {
        let token: String?
        tokenLock.lock(); token = cachedToken; tokenLock.unlock()
        guard let token else { return false }
        do {
            _ = try await http.send(.delete("api/push/subscribe/apns:\(token)"))
            return true
        } catch { return false }
    }

    /// Called by `AppDelegate.application(_:didRegisterForRemoteNotificationsWithDeviceToken:)`.
    public func deviceToken(_ data: Data) {
        let hex = Hex.encode(data)
        tokenLock.lock(); cachedToken = hex; tokenLock.unlock()
        waiters.publish(hex)
    }

    private let waiters = TokenWaiters()

    private func waitForToken(timeout seconds: TimeInterval) async -> String? {
        tokenLock.lock(); let cached = cachedToken; tokenLock.unlock()
        if let cached { return cached }
        return await waiters.nextOrTimeout(seconds)
    }

    private struct SubReq: Encodable { let endpoint: String; let p256dh: String; let auth: String }
}

/// Parks the first new token across all in-flight `enable()` coroutines.
private final class TokenWaiters: @unchecked Sendable {
    private let lock = NSLock()
    private var continuations: [CheckedContinuation<String?, Never>] = []

    func publish(_ token: String) {
        lock.lock(); let copy = continuations; continuations.removeAll(); lock.unlock()
        for c in copy { c.resume(returning: token) }
    }

    func nextOrTimeout(_ seconds: TimeInterval) async -> String? {
        await withCheckedContinuation { cont in
            lock.lock(); continuations.append(cont); lock.unlock()
            Task {
                try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
                self.lock.lock()
                // Timeout path — FIFO: if any continuation is still
                // pending, the oldest one wins the nil. A real impl
                // would key by ID; this bootstrap is precise enough for
                // the APNs 5-second window.
                if !self.continuations.isEmpty {
                    let c = self.continuations.removeFirst()
                    self.lock.unlock()
                    c.resume(returning: nil)
                } else {
                    self.lock.unlock()
                }
            }
        }
    }
}
