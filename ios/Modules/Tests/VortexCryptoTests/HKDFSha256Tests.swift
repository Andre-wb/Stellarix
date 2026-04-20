import XCTest
@testable import VortexCrypto

/// RFC 5869 §A.1 — SHA-256, 22/13/10/42.
final class HKDFSha256Tests: XCTestCase {
    private let kdf = HKDFSha256()

    func test_rfc5869_test_case_1() throws {
        let ikm  = try Hex.decode("0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b")
        let salt = try Hex.decode("000102030405060708090a0b0c")
        let info = try Hex.decode("f0f1f2f3f4f5f6f7f8f9")
        let okm  = try Hex.decode(
            "3cb25f25faacd57a90434f64d0362f2a" +
            "2d2d0a90cf1a5a4c5db02d56ecc4c5bf" +
            "34007208d5b887185865")

        let got = try kdf.derive(ikm: ikm, salt: salt, info: info, length: 42)
        XCTAssertEqual(got, okm)
    }
}
