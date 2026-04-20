import Foundation
import CryptoKit
import VortexCrypto

/// BIP39 generator — 256 bits of entropy → 24 words from the English
/// wordlist → PBKDF2-HMAC-SHA512 (2048 rounds) to a 64-byte seed.
public final class Bip39SeedProvider: SeedProvider {
    private let random: SecureRandomProvider
    private let wordlist: [String]

    public init(random: SecureRandomProvider, bundle: Bundle = .module) throws {
        self.random = random
        guard let url = bundle.url(forResource: "bip39_english", withExtension: "txt") else {
            throw SeedError.wordlistUnavailable
        }
        let raw = try String(contentsOf: url, encoding: .utf8)
        let words = raw.split(whereSeparator: \.isNewline).map { String($0).trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard words.count == 2048 else { throw SeedError.wordlistUnavailable }
        self.wordlist = words
    }

    public func generate() throws -> Mnemonic {
        let entropy = random.nextBytes(32)       // 256 bits
        let hash = SHA256.hash(data: entropy)
        let csByte = hash.prefix(1).first!

        // 256 bits entropy + 8 bits checksum = 264 bits = 24 × 11
        var bits = Array(repeating: false, count: 264)
        for i in 0..<32 {
            let b = Int(entropy[i])
            for k in 0..<8 { bits[i * 8 + k] = ((b >> (7 - k)) & 1) == 1 }
        }
        for k in 0..<8 { bits[256 + k] = ((Int(csByte) >> (7 - k)) & 1) == 1 }

        var words: [String] = []
        words.reserveCapacity(24)
        for i in 0..<24 {
            var idx = 0
            for k in 0..<11 { idx = (idx << 1) | (bits[i * 11 + k] ? 1 : 0) }
            words.append(wordlist[idx])
        }
        return try Mnemonic(words: words)
    }

    public func toSeed(mnemonic: Mnemonic, passphrase: Data) throws -> Data {
        // BIP39 spec: PBKDF2-HMAC-SHA512(password=mnemonic, salt="mnemonic" || passphrase,
        //                                 iterations=2048, dkLen=64)
        let passwordBytes = Array(mnemonic.phrase.decomposedStringWithCompatibilityMapping.utf8)
        var saltBytes: [UInt8] = Array("mnemonic".utf8)
        saltBytes.append(contentsOf: passphrase)
        return Pbkdf2HmacSha512.derive(password: passwordBytes, salt: saltBytes, iterations: 2048, length: 64)
    }
}

/// Minimal PBKDF2-HMAC-SHA512 using CryptoKit's HMAC primitive.
/// Enough for BIP39's fixed shape (iterations=2048, dkLen=64).
enum Pbkdf2HmacSha512 {
    static func derive(password: [UInt8], salt: [UInt8], iterations: Int, length: Int) -> Data {
        let key = SymmetricKey(data: password)
        let blockLen = 64     // SHA-512 output
        let blocks = Int((Double(length) / Double(blockLen)).rounded(.up))
        var dk = Data(capacity: blocks * blockLen)
        for i in 1...blocks {
            var saltAndIndex = Data(salt)
            saltAndIndex.append(UInt8((i >> 24) & 0xff))
            saltAndIndex.append(UInt8((i >> 16) & 0xff))
            saltAndIndex.append(UInt8((i >>  8) & 0xff))
            saltAndIndex.append(UInt8( i        & 0xff))
            var u = Data(HMAC<SHA512>.authenticationCode(for: saltAndIndex, using: key))
            var t = u
            for _ in 1..<iterations {
                u = Data(HMAC<SHA512>.authenticationCode(for: u, using: key))
                for j in 0..<blockLen { t[j] ^= u[j] }
            }
            dk.append(t)
        }
        return dk.prefix(length)
    }
}
