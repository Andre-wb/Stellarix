import Foundation

/// Cryptographic entropy source.
///
/// A thin protocol so tests can inject deterministic bytes (known-answer
/// RNG for RFC vectors) and so platform secure RNG can be swapped for a
/// Secure Enclave-backed impl on A-series / M-series devices in a later
/// wave — the caller stays oblivious.
public protocol SecureRandomProvider: Sendable {
    func nextBytes(_ length: Int) -> Data
}
