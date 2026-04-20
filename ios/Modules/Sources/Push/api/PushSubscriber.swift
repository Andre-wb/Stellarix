import Foundation

/// APNs push subscription. Implementation calls `application.registerForRemoteNotifications()`
/// + posts the device token (plus a generated X25519 pubkey + 16-byte auth
/// secret) to `/api/push/subscribe` so the node can encrypt payloads
/// end-to-end even through Apple's servers.
public protocol PushSubscriber: Sendable {
    func enable() async -> Bool
    func disable() async -> Bool
}
