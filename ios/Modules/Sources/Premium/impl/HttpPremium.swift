import Foundation
import Net

public actor HttpPremium: Premium {
    private let http: HttpClient
    public init(http: HttpClient) { self.http = http }

    private struct StartBody: Codable { let tier: String }
    private struct OkResp: Codable { let ok: Bool }

    public func status() async -> PremiumStatus? {
        try? await http.send(HttpRequest.get("/api/premium/status"), PremiumStatus.self)
    }
    public func startCheckout(tier: String) async -> CheckoutSession? {
        guard let req = try? HttpRequest.postJson("/api/premium/checkout", body: StartBody(tier: tier)) else { return nil }
        return try? await http.send(req, CheckoutSession.self)
    }
    public func cancel() async -> Bool {
        let req = HttpRequest(method: .POST, path: "/api/premium/cancel")
        return (try? await http.send(req, OkResp.self).ok) ?? false
    }
}
