import Foundation

/// Read-only view over the current JWT pair.
///
/// Net layer never mutates the session — only Auth does. Splitting the
/// interface keeps accidental overwrite paths impossible: an HTTP 401
/// handler can *ask* for a refresh but not invent one.
public protocol AuthTokenSource: Sendable {
    func accessToken() async -> String?
    func refreshToken() async -> String?
    /// Called on 401 — returns whether a fresh access token is now available.
    func refresh() async -> Bool
}
