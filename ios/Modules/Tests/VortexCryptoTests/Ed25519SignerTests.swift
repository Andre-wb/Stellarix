import XCTest
@testable import VortexCrypto

/// RFC 8032 §7.1 test 1 — empty message, deterministic signature.
final class Ed25519SignerTests: XCTestCase {
    private let signer = Ed25519Signer()

    func test_rfc8032_test1_sign_verify() throws {
        let sk  = try Hex.decode("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        let pk  = try Hex.decode("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        let msg = Data()
        let expected = try Hex.decode(
            "e5564300c360ac729086e2cc806e828a" +
            "84877f1eb8e5d974d873e065224901555" +
            "fb8821590a33bacc61e39701cf9b46bd" +
            "25bf5f0595bdfa987f990b6ec5b5a00")

        let sig = try signer.sign(privateKey: sk, message: msg)
        XCTAssertEqual(sig, expected)
        XCTAssertTrue(signer.verify(publicKey: pk, message: msg, signature: sig))
    }

    func test_verify_rejects_tampered_signature() throws {
        let kp = signer.generateKeyPair()
        let msg = Data("hello".utf8)
        var sig = try signer.sign(privateKey: kp.privateKey, message: msg)
        sig[0] ^= 0x01
        XCTAssertFalse(signer.verify(publicKey: kp.publicKey, message: msg, signature: sig))
    }
}
