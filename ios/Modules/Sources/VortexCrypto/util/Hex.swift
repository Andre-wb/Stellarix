import Foundation

/// Lowercase hex codec matching Python's `bytes.hex()` / `bytes.fromhex()`
/// and the Kotlin `Hex` object. Keeping one codec means subtle case /
/// 0x-prefix drift can never happen between clients.
public enum Hex {
    public static func encode(_ bytes: Data) -> String {
        let digits: [Character] = Array("0123456789abcdef")
        var out = String()
        out.reserveCapacity(bytes.count * 2)
        for b in bytes {
            let v = Int(b)
            out.append(digits[v >> 4])
            out.append(digits[v & 0x0F])
        }
        return out
    }

    public static func decode(_ s: String) throws -> Data {
        let lower = s.lowercased()
        guard lower.count % 2 == 0 else { throw HexError.oddLength }
        var out = Data(capacity: lower.count / 2)
        var i = lower.startIndex
        while i < lower.endIndex {
            let next = lower.index(i, offsetBy: 2)
            let pair = lower[i..<next]
            guard let byte = UInt8(pair, radix: 16) else { throw HexError.nonHex(String(pair)) }
            out.append(byte)
            i = next
        }
        return out
    }
}

public enum HexError: Error, Equatable {
    case oddLength
    case nonHex(String)
}
