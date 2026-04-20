import Foundation

/// Minimal HTTP surface consumed by every feature.
///
/// Keeping it protocol-first means tests wire a fake (recording) client
/// and feature impls never pin URLSession. `send` returns the decoded
/// body or throws — no `Result`, so callers use `try/catch` which plays
/// well with Swift's async.
public protocol HttpClient: Sendable {
    func send<T: Decodable>(_ req: HttpRequest, _ type: T.Type) async throws -> T
    func send(_ req: HttpRequest) async throws -> Data
}

public struct HttpRequest: Sendable {
    public enum Method: String, Sendable { case GET, POST, PUT, DELETE, PATCH }

    public var method: Method
    public var path: String
    public var body: Data?
    public var extraHeaders: [String: String]
    public var queryItems: [URLQueryItem]

    public init(
        method: Method,
        path: String,
        body: Data? = nil,
        extraHeaders: [String: String] = [:],
        queryItems: [URLQueryItem] = [],
    ) {
        self.method = method
        self.path = path
        self.body = body
        self.extraHeaders = extraHeaders
        self.queryItems = queryItems
    }

    public static func get(_ path: String, query: [URLQueryItem] = []) -> HttpRequest {
        .init(method: .GET, path: path, queryItems: query)
    }

    public static func postJson<T: Encodable>(_ path: String, body: T) throws -> HttpRequest {
        var req = HttpRequest(method: .POST, path: path, body: try JSONEncoder().encode(body))
        req.extraHeaders["Content-Type"] = "application/json"
        return req
    }

    public static func delete(_ path: String) -> HttpRequest {
        .init(method: .DELETE, path: path)
    }
}

public enum HttpError: Error, Equatable {
    case noBaseUrl
    case malformedUrl(String)
    case status(Int, body: String)
    case notJson
    case transport(String)
}
