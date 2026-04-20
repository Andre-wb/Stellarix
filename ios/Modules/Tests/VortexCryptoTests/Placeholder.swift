// Wave 2 populates this with RFC test vectors (RFC 5869 HKDF-SHA256,
// RFC 7748 X25519, RFC 8032 Ed25519, NIST GCM vectors, Argon2id KAT).
// The placeholder keeps the test target non-empty so SPM resolves it.
import XCTest
@testable import VortexCrypto

final class PlaceholderTests: XCTestCase {
    func test_moduleLoads() {
        XCTAssertEqual(VortexCryptoModule.version, "0.1.0")
    }
}
