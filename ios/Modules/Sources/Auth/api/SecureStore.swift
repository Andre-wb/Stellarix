import Foundation

/// Key/value store with OS-level encryption at rest.
///
/// Holds small secrets only (JWTs, seed phrase, per-device keys). Not
/// for bulk data — that goes to GRDB (Wave 7). Keeping the surface
/// narrow lets us swap the Keychain-backed impl for a hardware-enclave
/// one without any call-site churn.
public protocol SecureStore: Sendable {
    func getString(_ key: String) -> String?
    func setString(_ key: String, _ value: String?)
    func clear()
}
