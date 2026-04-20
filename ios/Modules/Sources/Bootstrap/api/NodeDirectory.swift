import Foundation

/// Locates reachable Vortex nodes at first launch.
///
/// Single responsibility: turn "the user just opened the app, we have
/// no config" into a working base URL or a clear "can't reach anyone"
/// signal. Parsing, storage, UI all live elsewhere.
public protocol NodeDirectory: Sendable {
    func probePrimary() async -> ProbeResult
    func probe(url: String) async -> ProbeResult
}

public enum ProbeResult: Sendable, Equatable {
    case ok(baseUrl: String, version: String?)
    case unreachable(tried: String, reason: String)
}
