import Foundation

/// Stripe/crypto payments wrapper. Not tied to an SDK — all calls go
/// through the node which talks to the configured processor server-
/// side. Client just shows status and surfaces the checkout URL.
public struct PremiumStatus: Sendable, Codable, Equatable {
    public let tier: String             // "free" | "plus" | "pro"
    public let renewsAt: Int64?         // unix ms
    public let cancelledAt: Int64?
    public let features: [String]       // ["scheduled","larger_uploads",…]
    public init(tier: String, renewsAt: Int64?, cancelledAt: Int64?, features: [String]) {
        self.tier = tier; self.renewsAt = renewsAt; self.cancelledAt = cancelledAt; self.features = features
    }
}

public struct CheckoutSession: Sendable, Codable {
    public let url: String
    public let id: String
    public init(url: String, id: String) { self.url = url; self.id = id }
}

public protocol Premium: Sendable {
    func status() async -> PremiumStatus?
    func startCheckout(tier: String) async -> CheckoutSession?
    func cancel() async -> Bool
}
