import Foundation
import Net

/// STUN / TURN servers fetched from the node's `/v1/calls/ice`.
/// List changes when the operator rotates TURN creds, so [CallController]
/// refreshes on every new call instead of caching forever.
public final class HttpIceConfigProvider: IceConfigProvider {
    private let http: HttpClient

    public init(http: HttpClient) { self.http = http }

    public func current() async -> [IceServer] {
        do {
            let resp = try await http.send(.get("v1/calls/ice"), IceResp.self)
            return resp.servers.map {
                IceServer(urls: $0.urls, username: $0.username, credential: $0.credential)
            }
        } catch {
            // Fall back to Google's public STUN so a fresh install can at
            // least complete peer discovery on unrestricted networks.
            return [IceServer(urls: ["stun:stun.l.google.com:19302"])]
        }
    }

    private struct IceDto: Decodable {
        let urls: [String]
        let username: String?
        let credential: String?
    }
    private struct IceResp: Decodable { let servers: [IceDto] }
}
