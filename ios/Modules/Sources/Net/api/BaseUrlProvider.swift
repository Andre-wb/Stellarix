import Foundation

/// Current node base URL source. Read-only — write path belongs to
/// Bootstrap, this keeps the layering enforced by the compiler.
public protocol BaseUrlProvider: Sendable {
    func current() -> String?
}
