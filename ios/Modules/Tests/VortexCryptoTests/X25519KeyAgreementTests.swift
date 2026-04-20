import XCTest
@testable import VortexCrypto

/// RFC 7748 §5.2 — Alice/Bob shared-secret vector + round-trip.
final class X25519KeyAgreementTests: XCTestCase {
    private let ka = X25519KeyAgreement()

    func test_rfc7748_alice_bob_shared_secret() throws {
        let alicePriv = try Hex.decode("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
        let bobPub    = try Hex.decode("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
        let expected  = try Hex.decode("4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742")

        let shared = try ka.agree(myPrivate: alicePriv, theirPublic: bobPub)
        XCTAssertEqual(shared, expected)
    }

    func test_round_trip() throws {
        let a = ka.generateKeyPair()
        let b = ka.generateKeyPair()
        let sAB = try ka.agree(myPrivate: a.privateKey, theirPublic: b.publicKey)
        let sBA = try ka.agree(myPrivate: b.privateKey, theirPublic: a.publicKey)
        XCTAssertEqual(sAB.count, 32)
        XCTAssertEqual(sAB, sBA)
    }
}
