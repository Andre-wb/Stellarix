import XCTest
@testable import VortexCrypto

final class Argon2idHasherTests: XCTestCase {
    private let hasher = Argon2idHasher()
    /// Deliberately tiny so CI stays fast — production uses `.interactive()`.
    private let cheap = Argon2Params(iterations: 1, memoryKiB: 1024, parallelism: 1, hashLen: 32)

    func test_verify_accepts_matching_password() throws {
        let salt = Data(repeating: 0xAA, count: 16)
        let hash = try hasher.hash(password: Data("correct horse battery staple".utf8), salt: salt, params: cheap)
        XCTAssertTrue(try hasher.verify(
            password: Data("correct horse battery staple".utf8),
            salt: salt, expected: hash, params: cheap))
    }

    func test_verify_rejects_wrong_password() throws {
        let salt = Data(count: 16)
        let hash = try hasher.hash(password: Data("secret".utf8), salt: salt, params: cheap)
        XCTAssertFalse(try hasher.verify(
            password: Data("SECRET".utf8),
            salt: salt, expected: hash, params: cheap))
    }

    func test_different_salts_yield_different_hashes() throws {
        let h1 = try hasher.hash(password: Data("pw".utf8), salt: Data(repeating: 0, count: 16), params: cheap)
        let h2 = try hasher.hash(password: Data("pw".utf8), salt: Data(repeating: 1, count: 16), params: cheap)
        XCTAssertNotEqual(h1, h2)
    }
}
