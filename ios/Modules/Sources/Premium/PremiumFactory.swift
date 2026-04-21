import Foundation
import Net

public struct PremiumFactory {
    public let premium: Premium
    public init(http: HttpClient) { self.premium = HttpPremium(http: http) }
}
