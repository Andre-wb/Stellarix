import Foundation
import Net

public struct WSFactory {
    public let client: WsClient

    public init(base: BaseUrlProvider, tokens: AuthTokenSource) {
        self.client = URLSessionWsClient(base: base, tokens: tokens)
    }
}
