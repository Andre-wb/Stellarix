import Foundation

/// Composition root for the iOS app.
///
/// Swift doesn't have Hilt-style code-gen DI; instead we construct the
/// whole object graph in one place and pass the dependencies each
/// screen needs as its ViewModel inputs. This keeps the wiring visible
/// (unlike runtime DI containers) and preserves the SOLID contract —
/// screens still depend only on feature protocols, never concrete types.
///
/// Later waves replace the stubs below with real module initialisers.
public final class AppEnvironment {

    public static let shared = AppEnvironment()

    /// Version string surfaced in the brand screen + about dialog.
    public let version: String = "0.1.0"

    private init() {}
}
