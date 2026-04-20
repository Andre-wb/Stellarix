import XCTest
@testable import VortexCrypto

final class HexTests: XCTestCase {
    func test_round_trip() throws {
        let bytes = Data([0x00, 0x01, 0x7f, 0x80, 0xff])
        let hex = Hex.encode(bytes)
        XCTAssertEqual(hex, "00017f80ff")
        XCTAssertEqual(try Hex.decode(hex), bytes)
    }

    func test_odd_length_rejected() {
        XCTAssertThrowsError(try Hex.decode("abc")) { err in
            XCTAssertEqual(err as? HexError, .oddLength)
        }
    }

    func test_non_hex_rejected() {
        XCTAssertThrowsError(try Hex.decode("zz")) { err in
            XCTAssertEqual(err as? HexError, .nonHex("zz"))
        }
    }
}
