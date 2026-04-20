import Foundation
import Net
import WS

public struct CallsFactory {
    public let controller: WebRtcCallController
    public let ice: IceConfigProvider

    public init(http: HttpClient, ws: WsClient) {
        let ice = HttpIceConfigProvider(http: http)
        self.ice = ice
        self.controller = WebRtcCallController(ws: ws, ice: ice)
    }
}
