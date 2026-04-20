import XCTest
@testable import VortexCrypto

/// Round-trip + AAD binding + tamper detection. NIST-style static KAT
/// isn't useful here because every encryption uses a random nonce, so
/// ciphertext is non-deterministic by design.
final class AESGCMAeadTests: XCTestCase {
    private let aead = AESGCMAead(random: SystemSecureRandom())

    func test_encrypt_then_decrypt_round_trips() throws {
        let key = Data((0..<32).map { UInt8($0) })
        let pt  = Data("hello vortex".utf8)
        let packed = try aead.encrypt(key: key, plaintext: pt)
        let out    = try aead.decrypt(key: key, packed: packed)
        XCTAssertEqual(out, pt)
    }

    func test_aad_must_match_on_decrypt() throws {
        let key = Data(count: 32)
        let pt  = Data("test".utf8)
        let packed = try aead.encrypt(key: key, plaintext: pt, aad: Data("room42".utf8))
        XCTAssertThrowsError(try aead.decrypt(key: key, packed: packed, aad: Data("room99".utf8)))
    }

    func test_bit_flip_is_detected() throws {
        let key = Data(count: 32)
        var packed = try aead.encrypt(key: key, plaintext: Data("data".utf8))
        packed[packed.count - 1] ^= 0x01
        XCTAssertThrowsError(try aead.decrypt(key: key, packed: packed))
    }
}
