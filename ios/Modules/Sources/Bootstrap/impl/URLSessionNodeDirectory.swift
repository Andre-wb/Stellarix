import Foundation

/// URLSession-backed [NodeDirectory].
///
/// Wave 3 probes the primary URL (hard-coded — DoH gateway comes in a
/// later wave) via `GET <url>/v1/integrity`. `status: "verified"` ⇒ ok;
/// anything else (timeout, non-2xx, bad JSON) ⇒ `.unreachable`.
public final class URLSessionNodeDirectory: NodeDirectory {
    private let session: URLSession
    private let primary: String

    public init(primary: String = "https://vortexx.sol") {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 7
        cfg.timeoutIntervalForResource = 7
        self.session = URLSession(configuration: cfg)
        self.primary = primary
    }

    public func probePrimary() async -> ProbeResult { await probe(url: primary) }

    public func probe(url: String) async -> ProbeResult {
        guard let clean = normalize(url) else {
            return .unreachable(tried: url, reason: "malformed_url")
        }
        let probeUrl = "\(clean)/v1/integrity"
        guard let u = URL(string: probeUrl) else {
            return .unreachable(tried: probeUrl, reason: "malformed_url")
        }
        do {
            let (data, response) = try await session.data(from: u)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                return .unreachable(tried: probeUrl, reason: "http_\(code)")
            }
            let dto = try JSONDecoder().decode(IntegrityDto.self, from: data)
            if dto.status == "verified" {
                return .ok(baseUrl: clean, version: dto.version)
            }
            return .unreachable(tried: probeUrl, reason: "status_\(dto.status ?? "nil")")
        } catch {
            return .unreachable(tried: probeUrl, reason: (error as NSError).localizedDescription)
        }
    }

    private func normalize(_ url: String) -> String? {
        var trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        while trimmed.hasSuffix("/") { trimmed.removeLast() }
        if trimmed.isEmpty { return nil }
        let withScheme = trimmed.contains("://") ? trimmed : "https://\(trimmed)"
        return URL(string: withScheme)?.host != nil ? withScheme : nil
    }

    private struct IntegrityDto: Decodable {
        let status: String?
        let version: String?
    }
}
