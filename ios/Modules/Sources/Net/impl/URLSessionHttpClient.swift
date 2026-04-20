import Foundation

/// URLSession-backed [HttpClient].
///
/// Behaviour:
///   * base URL is prepended to every relative path
///   * Authorization header added if [AuthTokenSource] has an access token
///   * 401 triggers one automatic `refresh()` + retry (single retry, no loop)
///   * transient 5xx / IO are retried twice with exponential backoff
public final class URLSessionHttpClient: HttpClient {
    private let session: URLSession
    private let base: BaseUrlProvider
    private let tokens: AuthTokenSource
    private let decoder: JSONDecoder

    public init(
        base: BaseUrlProvider,
        tokens: AuthTokenSource,
        configure: (URLSessionConfiguration) -> Void = { _ in },
    ) {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 15
        cfg.timeoutIntervalForResource = 30
        configure(cfg)
        self.session = URLSession(configuration: cfg)
        self.base = base
        self.tokens = tokens
        self.decoder = JSONDecoder()
    }

    public func send<T: Decodable>(_ req: HttpRequest, _ type: T.Type) async throws -> T {
        let data = try await send(req)
        do { return try decoder.decode(T.self, from: data) }
        catch { throw HttpError.notJson }
    }

    public func send(_ req: HttpRequest) async throws -> Data {
        let attempt = { [self] (includeAuth: Bool) -> (Data, HTTPURLResponse) in
            let urlRequest = try await buildRequest(req, includeAuth: includeAuth)
            let (data, response) = try await session.data(for: urlRequest)
            guard let http = response as? HTTPURLResponse else {
                throw HttpError.transport("not HTTP response")
            }
            return (data, http)
        }

        var lastStatus: Int = 0
        for retry in 0..<3 {
            do {
                let (data, http) = try await attempt(true)
                switch http.statusCode {
                case 200..<300:
                    return data
                case 401 where retry == 0:
                    if await tokens.refresh() { continue }
                    throw HttpError.status(401, body: body(data))
                case 500..<600:
                    lastStatus = http.statusCode
                    try await Task.sleep(nanoseconds: UInt64(pow(2.0, Double(retry)) * 500_000_000))
                    continue
                default:
                    throw HttpError.status(http.statusCode, body: body(data))
                }
            } catch let err as HttpError {
                throw err
            } catch {
                lastStatus = -1
                if retry == 2 { throw HttpError.transport((error as NSError).localizedDescription) }
                try await Task.sleep(nanoseconds: UInt64(pow(2.0, Double(retry)) * 500_000_000))
            }
        }
        throw HttpError.status(lastStatus, body: "retry limit")
    }

    // ── internals ──────────────────────────────────────────────────────

    private func buildRequest(_ req: HttpRequest, includeAuth: Bool) async throws -> URLRequest {
        guard var baseStr = base.current(), !baseStr.isEmpty else { throw HttpError.noBaseUrl }
        while baseStr.hasSuffix("/") { baseStr.removeLast() }
        let relative = req.path.hasPrefix("/") ? req.path : "/\(req.path)"
        var comps = URLComponents(string: baseStr + relative)
        if !req.queryItems.isEmpty { comps?.queryItems = req.queryItems }
        guard let url = comps?.url else { throw HttpError.malformedUrl(relative) }

        var ur = URLRequest(url: url)
        ur.httpMethod = req.method.rawValue
        ur.httpBody = req.body
        for (k, v) in req.extraHeaders { ur.setValue(v, forHTTPHeaderField: k) }
        if includeAuth, let t = await tokens.accessToken(), !t.isEmpty {
            ur.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
        }
        return ur
    }

    private func body(_ data: Data) -> String {
        String(data: data.prefix(200), encoding: .utf8) ?? ""
    }
}
